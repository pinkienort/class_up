#!/usr/bin/env python

import sys
import os
import argparse
from pprint import pprint as pp
import pickle

import numpy as np

_DEFAULT_MAX_INT = -10000
_DEFAULT_MIN_INT =  10000


def main():

    parser = argparse.ArgumentParser(description='Hypernyming synsets in Imagenet')
    parser.add_argument('isa', help='Path to isa file')
    parser.add_argument('synsets', help='Path to synsets file')
    parser.add_argument('train', help='Path to train pairs file')
    parser.add_argument('val', help='Path to val pairs file')
    parser.add_argument('--out', default='res',
            help='Path to output directory')
    parser.add_argument('--num_synsets', default=100, type=int,
            help='Number of synsets of subset')
    parser.add_argument('--use_pickle', default=False, action='store_true',
            help='Flag to enable loading pickle objects')
    parser.add_argument('--write_individual', default=False, action='store_true',
            help="""Flag to write the pairs to evaluate each reference synset.
            In this mode, `num_synsets` is ignored.""")
    args = parser.parse_args()

    ## init
    print("Loading isa file: {}".format(args.isa))
    isa = Isa(args.isa)
    print("Loading synsets file: {}".format(args.synsets))
    synsets = Synsets(args.synsets)

    num_synsets = args.num_synsets

    pickle_synsets = os.path.join(args.out, 'synsets.pickle.py')
    if os.path.isfile(pickle_synsets) and args.use_pickle:
        print("Loading pickle of synsets.")
        with open(pickle_synsets, 'rb') as f:
            synsets = pickle.load(f)
    else:
        synsets.make_subset(isa, num_synsets)
        print("Dumping pickle of synsets.")
        with open(pickle_synsets, 'wb') as f:
            pickle.dump(synsets, f)
    print("Writing subset synsets.")
    synsets.write_subset(os.path.join(args.out, 'synsets.txt'))

    def pairs_process(pairs, subset, out, num):
        basename = os.path.basename(pairs).split('.')[0]

        print("Loading pairs file: {}".format(pairs))
        pairs = Pairs(pairs)

        pickle_pairs = os.path.join(out, "{}-pairs.pickle.py".format(basename))
        if os.path.isfile(pickle_pairs) and args.use_pickle:
            print("Loading pickle of {} pairs".format(basename))
            with open(pickle_pairs, 'rb') as f:
                pairs = pickle.load(f)
        else:
            print("Making list of selected pairs")
            pairs.make_selected_pairs(subset)
            print("Selecting pairs")
            pairs.select_pairs(num, subset)
            # print("Making list of subset labels.")
            # pairs.add_subset_label_all(subset)
            # print("Making list of reference_labels.")
            # pairs.add_reference_labels_all(subset)
            print("Dumping list of pairs")
            with open(pickle_pairs, 'wb') as f:
                pickle.dump(pairs, f)

        print("Writing subset pairs with new label")
        pairs.write_subset_all(os.path.join(out, basename + "-subset.txt"))
        print("Writing original and reference pairs with multi labels")
        pairs.write_reference_and_original(os.path.join(out, basename + "-org-ref.txt"))

    def pairs_eval_individual(pairs, subset, out):
        basename = os.path.basename(pairs).split('.')[0]

        print("Loading val pairs file: {}".format(pairs))
        pairs = Pairs(pairs)
        print("Making list of reference_labels.(last_level_subset)")
        pairs.add_reference_labels(subset)
        print("Writing reference pairs individually")

        try:
            os.makedirs(os.path.join(out, basename))
        except:
            pass
        for synset in subset:
            pairs.write_individual_reference(
                    synset,
                    os.path.join(out, "{}/{}-{}.txt". format(
                        basename, 'reference', synset.org_synset)))

    # NOTE: Uncomment the next line, pairs_process for train pairs,
    # only in production mode. Because train pairs file has a lot of lines.
    if args.write_individual:
        pairs_eval_individual(args.train, synsets.last_level_subset, args.out)
        pairs_eval_individual(args.val, synsets.last_level_subset, args.out)
    else:
        pairs_process(args.train, synsets.subset, args.out, Synset.NUM_IMAGES_TRAIN)
        pairs_process(args.val, synsets.subset, args.out, Synset.NUM_IMAGES_VAL)


class Isa:

    def __init__(self, path):
        self.isa = [l.split() for l in open(path).read().strip().split('\n')]

    def search_parents(self, synset):
        """Return parents corresponded with `synset'.
        The retuned array is sorted."""
        parents = []
        for parent, child in self.isa:
            if (synset == child):
                parents.append(parent)
        return sorted(parents)

    def search_children(self, synset):
        """Return children corresponded with `synset'.
        The retuned array is sorted like `search_parents'."""
        children = []
        for parent, child in self.isa:
            if (synset == parent):
                children.append(child)
        return sorted(children)


class Synset:

    # trainはまちまちである。1クラスの最大枚数を越えないようにすりゅ。
    NUM_IMAGES_TRAIN = 1300 # 最大枚数
    # validationは各クラス50枚保証されいてる
    NUM_IMAGES_VAL   = 50

    def __init__(self, synset, label):
        """Constructor of Sysnet class.
        `synset' is String like `n12345667'. `label' is Integer
        for the synset. `org_*' is stored as single data type, not array.
        On the other hands, `current_*' includes `org_*` and the synsets and
        labels which is belong to `parents'. And it is possible that `parents'
        is not only one.

            org_synset<String>: a synset given at the initialization.
            org_label<Integer>: also like `org_synset'.
            parents<List>: 2-d array of parents for both `org_synset' and
                the parents of parents. n-th parents are managed with
                `self.index'.
            current_synsets<Array>: If `level` is 0, return
                `org_label`. Else, return n-th parents.
            level: this is indicate n-th of parents.
            common_root_synsets<Array>: a set of sysnets, all of which has
                `current_synsets'.
            common_root_labels<Array>: also like `common_root_synsets'
            is_root: this indiates that this synset cannot hypernnym anymore."""

        self.org_synset = synset
        self.org_label = label
        self.parents = []
        self.level = 0
        self.is_root = False
        self.common_root_synsets = []

    @property
    def currents(self):
        """Current synsets.
        Return array of synsets which is corresponded the level."""
        if self.level is 0:
            return [self.org_synset]
        # 1 in the level is meant first parents, equal to parents[0]
        return self.parents[self.level - 1]

    def add_parents(self, parents):
        """Add parents synsets to the `self.synsets'
        `len(parents)' is 0, a flag, `self.is_root' is set to True"""
        if len(parents) > 0:
            self.parents.append(parents)
        else:
            self.is_root = True

    def go_parent(self):
        """Hypernym the synset.
        If the synset can go Hypernym one, return the level.
        Else if the synset is a top of tree, return -1 as exception."""
        if self.level < len(self.parents):
            self.level += 1
            return self.level
        return -1 # parent is root(末端)

    def go_child(self):
        """Hyponym the synset.
        If the synset can go Hyponym one, decrease the level by 1, and
        return the level. Else if the synset is original synset which is
        treated as a 'leaf', return -1 as a exception."""
        if self.level > 0:
            self.level -= 1
            return self.level
        return -1 # child is leaf(末端)

    @property
    def common_root_labels(self):
        labels = []
        labels.append(self.org_label)
        for synset in self.common_root_synsets:
            labels.append(synset.org_label)
        return labels

    def has_org_label(self, label):
        if (self.org_label == label):
            return True
        return False

    def has_common_root_labels(self, label):
        if (self.has_org_label(label)):
            return True
        elif (self._has_reference_root_labels(label)):
            return True
        return False

    def _has_reference_root_labels(self, label):
        for synset in self.common_root_synsets:
            if (synset.org_label == label):
                return True
        return False

    def remove_currents(self):
        self.parents.pop()


class Synsets:

    def __init__(self, path):
        self.synsets = [Synset(s,i) for i,s in enumerate(open(path).read().strip().split('\n'))]
        self.subset = None
        self.last_level_subst = None

    def __len__(self):
        """ Length of synsets at when each synsets have n-th parents"""
        arr = []
        for synset in self.synsets:
            for current_synset in synset.currents:
                arr.append(current_synset)
        return len(set(arr))

    def check_len(self):
        # __len__(self)が間違っていたので、check_len(self)を別に実装。
        d = self.get_dictionary_of_common_root_synsets()
        return len(d.keys())

    def get_dictionary_of_common_root_synsets(self):
        def check_synset_list(synset, synsets):
            if synset in synsets:
                return True
        def check_common_root_synset(i, synsets):
            if i in synsets.keys():
                return True
            for arr in synsets.values():
                if i in arr: # 祖先が同じ
                    return True
            return False
        common_root_synsets = {} # synsetsのindexで管理
        for i, i_synset in enumerate(self.synsets):
            if check_common_root_synset(i, common_root_synsets):
                # 祖先が同じi、最初に見つかった代表ラベルの、甥姪として
                # 既に追加されているのでスキップ
                continue
            # 先祖全てを1つの配列に
            i_all_parents = [p for parr in i_synset.parents for p in parr]
            for j, j_synset in enumerate(self.synsets):
                if i == j: # 自分自身はスキップ
                    continue
                j_all_parents = [p for parr in j_synset.parents for p in parr]
                for i_s in i_all_parents: # i_s as sysnet
                    if check_synset_list(i_s, j_all_parents): # i_synsetとj_synsetが同じ先祖を持つ
                        if not i in common_root_synsets.keys():
                            # 最初に見つかった場合は、代表クラス
                            common_root_synsets[i] = []
                        common_root_synsets[i].append(j)
                        break
                if not i in common_root_synsets.keys():
                    # 同じ先祖を1つも持たないやつ
                    common_root_synsets[i] = []
        return common_root_synsets

    def make_subset(self, isa, num_synsets=100):
        print("Making subset of synsets.")
        # 与えられたsynsetsから目標の数までHypernymingする
        level = 1
        multi_parents = {}
        def report_multi_parents(synsets):
            num_max = _DEFAULT_MAX_INT
            num_min = _DEFAULT_MIN_INT
            for synset in synsets:
                num_parents = len(synset.parents[-1])
                num_max = max(num_parents, num_max)
                num_min = min(num_parents, num_min)
            print("number of multi parents: {}".format(len(synsets)))
            print("max of multi_parents   : {}".format(num_max))
            print("min of multi_parents   : {}".format(num_min))
        def search_parents_for_current_synsets(currents, isa):
            parents_for_currents = []
            for current_synset in currents:
                for synset in isa.search_parents(current_synset):
                    parents_for_currents.append(synset)
            return list(set(parents_for_currents)) # remove duplicates and sorted by set()
        while self.check_len() >= num_synsets:
            print("Level: {} | Number of synsets: {}".format(
                level, self.check_len()))
            # multi_parents[level] = []
            for synset in self.synsets:
                # 親が1つでない場合あるので配列
                parents = search_parents_for_current_synsets(synset.currents, isa)
                if len(parents) == 0:
                    synset.is_root = True
                    continue
                # if len(parents) > 1:
                #     multi_parents[level].append(synset)
                synset.add_parents(parents)
                synset.go_parent()
            # report_multi_parents(multi_parents[level])
            level += 1
        print("Reached last level")
        print("Level: {} | Number of synsets: {}".format(
                level, self.check_len()))

        # 上のwhileで目標数を下回るため、深さを1つだけ戻す
        for synset in self.synsets:
            synset.go_child()
            synset.remove_currents()

        assert self.check_len() >= num_synsets, "Error: number of synsets is too few"


        # 重複を調べる。もとのsynsetがHypernymingしたときに到達するsynset
        # を持つ、同階層レベルのsynsetの有無を調べる。

        # 同じrootを持つ共通のsynsetを調べ、最初にヒットしたsynsetを
        # 代表としてlast_level_subsetに追加する

        # 一番上の親であるsynset.currentsだけでなく全て親である
        # synset.parentsを全て見る方法でないと、途中でcommon_root_synsetになった場合、
        # 検出できない。そのため、上の方法はやめ。
        common_root_synsets = self.get_dictionary_of_common_root_synsets()
        # pp(len(common_root_synsets))
        # pp(common_root_synsets)

        last_level_subset = []
        for key, values in common_root_synsets.items(): # key is index for synset(i) in check_len()
            synset = self.synsets[key]
            for value in values: # value is index for synset(j) in check_len()
                synset.common_root_synsets.append(self.synsets[value])
            last_level_subset.append(synset)
        self.last_level_subset = last_level_subset

        # subsetのsynsetのlabelはsubsetの順番
        # 順番通りに取り出すと、認識率が高いsynsetや低いsynsetの傾向を
        # 知らずに取り出してしまうので、別途調べてからsubsetを作るやり方を採用。
        # laod_subset_order()

        # ランダムに100個選ぶ
        np.random.shuffle(self.last_level_subset)
        self.subset = self.last_level_subset[:num_synsets]
        print("Number of synset in subset: {}". format(len(self.subset)))

        for synset in self.subset:
            str_labels = [str(l) for l in synset.common_root_labels]
            print("org_label: {0:3d} | common_root_labels: {1}". format(synset.org_label, " ".join(str_labels)))

    def load_subset_order(self):
        pass

    def write_subset(self, out):
        """Writing synsets of subset. The synset is original synset instead of
        hypernymed one."""
        with open(out, 'w') as f:
            for synset in self.subset:
                # 画像の元ラベルと対応させるためにoriginalのsynsetを書き込む
                f.write("{}\n".format(synset.org_synset))


class Pair:

    def __init__(self, image_path, label):
        self.image_path = image_path
        self.org_label = label
        self.reference_labels = []
        self.subset_label = None


class Pairs:

    def __init__(self, path):
        self.org_pairs = []
        for line in open(path).read().strip().split('\n'):
            image_path, label = line.split()
            self.org_pairs.append(Pair(image_path, int(label)))

    def make_selected_pairs(self, subset):
        # last_level_subsetからsubsetを引いたsynsetsに該当するsynsetを除外する
        pairs = []
        labels = set([label for synset in subset for label in synset.common_root_labels])
        for pair in self.org_pairs:
            if pair.org_label in labels:
                pairs.append(pair)
        self.pairs = pairs

    def add_reference_labels(self, subset):
        def get_reference_labels(label, subset):
            for synset in subset:
                if (synset.has_org_label(label)):
                    return synset.common_root_labels
            return None
        for pair in self.pairs:
            pair.reference_labels = get_reference_labels(pair.org_label, subset)

    def add_reference_labels_all(self, subset):
        def get_reference_labels(label, subset):
            labels = []
            for synset in subset:
                if synset.has_common_root_labels(label):
                    # 1つのsynsetにたどり着ける可能性は1つではない
                    labels += synset.common_root_labels
            return list(set(labels))
        for pair in self.pairs:
            pair.reference_labels = get_reference_labels(pair.org_label, subset)

    def add_subset_label(self, subset):
        """Adding the label which is in subset. Search key is label of pair.
        If the target label is founed, take the label from subset of synsets.
        Else, return `None'"""
        def get_subset_label(label, subset):
            for index, synset in enumerate(subset): # index as label
                if (synset.has_org_label(label)):
                    return index
            return None
        for pair in self.pairs:
            pair.subset_label = get_subset_label(pair.org_label, subset)

    def add_subset_label_all(self, subset):
        """Adding the label which is in subset. Search key is label of pair.
        If the target label is founed, take the label from subset of synsets.
        Else, return `None'"""
        def get_subset_label(label, subset):
            indexes = []
            for index, synset in enumerate(subset): # index as label
                if synset.has_common_root_labels(label):
                    # 1つのsynsetにたどり着ける可能性は1つではない
                    # get_reference_label_allと同様
                    indexes.append(index)
            np.random.shuffle(indexes)
            return indexes[0]
        for pair in self.pairs:
            pair.subset_label = get_subset_label(pair.org_label, subset)

    def select_pairs(self, num, subset):
        # subset_label毎にpairをまとめる
        def create_selected_pairs(synset, num):
            selected_pairs = []
            # pairの重複が考えられるので、pair loopをsubset_labelごとに回す
            for pair in self.pairs:
                if pair.org_label in synset.common_root_labels:
                    selected_pairs.append(pair)
            num = len(selected_pairs) if len(selected_pairs) < num else num
            np.random.shuffle(selected_pairs)
            return selected_pairs[:num]

        self.selected_pairs = {}
        for index, synset in enumerate(subset):
            self.selected_pairs[index] = {
                    'pairs': create_selected_pairs(synset, num),
                    'common_root_labels': synset.common_root_labels,
                    'subset_label': index }

    def write_reference(self, out):
        """Also `writing_subset', this method writes only pairs related with
        subset synsets only"""
        with open(out, 'w') as f:
            for pair in self.pairs:
                if pair.reference_labels is not None:
                    f.write("{} ".format(pair.image_path))
                    str_labels = [str(l) for l in pair.reference_labels]
                    f.write("{}\n".format(" ".join(str_labels)))

    def write_reference_all(self, out):
        """Also `writing_subset', this method writes only pairs related with
        subset synsets only"""
        with open(out, 'w') as f:
            for pairs in self.selected_pairs.values():
                for pair in pairs:
                    str_labels = [str(l) for l in pair.reference_labels]
                    f.write("{} {}\n".format(
                        pair.image_path, " ".join(str_labels)))

    def write_reference_and_original(self, out):
        """Also `writing_subset', this method writes only pairs related with
        subset synsets only"""
        with open(out, 'w') as f:
            for key, pairs in self.selected_pairs.items():
                # print('subset_label: {} | common_root_labels: {}'
                #         . format(pairs['subset_label'],
                #             " ".join([str(l) for l in pairs['common_root_labels']])))
                common_root_labels = pairs['common_root_labels']
                pairs = pairs['pairs']
                for pair in pairs:
                    org_label = pair.org_label
                    common_root_labels_wo_org = list(
                            set([org_label]) ^
                            set(common_root_labels))
                    str_labels = [str(l) for l in common_root_labels_wo_org]
                    f.write("{} {} {}\n".format( pair.image_path, org_label, " ".join(str_labels)))
                    # print("img: {} | org_label: {} | wo_org: {}"
                    #         .format( pair.image_path, org_label, " ".join(str_labels)))


    def write_subset(self, out):
        """Writing pairs rejated with subset synsets only.
        If a label of the pair is not found, the pair line is not write."""
        with open(out, 'w') as f:
            for pair in self.pairs:
                if pair.subset_label is not None:
                    f.write("{} {}\n".format(pair.image_path, pair.subset_label))

    def write_subset_all(self, out):
        """Writing pairs related with subset synsets only.
        If a label of the pair is not found, the pair line is not write."""
        with open(out, 'w') as f:
            for key, pairs in self.selected_pairs.items(): # key is subset label
                # print("subset_label: {} | len(pairs): {}"
                #         . format(pairs['subset_label'], len(pairs['pairs'])))
                subset_label = pairs['subset_label']
                pairs = pairs['pairs']
                for pair in pairs:
                    f.write("{} {}\n". format(pair.image_path, subset_label))

    def write_original_all(self, out):
        """Also `writing_subset', this method writes only pairs related with
        subset synsets only"""
        with open(out, 'w') as f:
            for pairs in self.selected_pairs.values():
                for pair in pairs:
                    f.write("{} {}\n".format(pair.image_path, pair.org_label))

    def write_individual_reference(self, synset, out):
        lines = []
        for pair in self.pairs:
            if pair.org_label == synset.org_label:
                str_labels = [str(l) for l in pair.reference_labels]
                s = "{} {}\n". format(pair.image_path, " ".join(str_labels))
                lines.append(s)
        with open(out, 'w') as f:
            for line in lines:
                f.write(line)


if __name__ == "__main__":
    main()
