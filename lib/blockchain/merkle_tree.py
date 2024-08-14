from samson.core.base_object import BaseObject
import math

class MerkleTree(BaseObject):
    def __init__(self, hash_func):
        self.leaves    = []
        self.hashes    = []
        self.item_loc  = {}
        self.hash_func = hash_func


    @property
    def root(self):
        assert len(self.hashes[-1]) == 1
        return self.hashes[-1][0]


    def add_leaf(self, item: object):
        self.leaves.append((item.hash(), item))
        self.item_loc[item.hash()] = len(self.leaves)-1

        depth   = math.ceil(math.log2(len(self.leaves)))
        updated = item.hash()

        for i in range(depth+1):
            if len(self.hashes) < (i+1):
                self.hashes.append([])

            self.hashes[i].append(updated)
            if len(self.hashes[i]) % 2:
                break
            else:
                l,r     = self.hashes[i][-2:]
                updated = self.hash_func(l+r)


    def generate_proof(self, item):
        idx   = self.item_loc[item.hash()]
        depth = math.ceil(math.log2(len(self.leaves)))
        path  = []

        for i in range(depth):
            curr_loc = (idx >> i)
            path.append(self.hashes[i][curr_loc + 1 - 2*(curr_loc % 2)])

        return mt.root, path, idx
    

    def verify(self, item, root, path: list, index: int):
        curr_hash = item.hash()

        for i, other_hash in enumerate(path):
            curr_loc = (index >> i) & 1
            if curr_loc:
                l,r = other_hash, curr_hash
            else:
                l,r = curr_hash, other_hash

            curr_hash = self.hash_func(l+r)
        
        return curr_hash == root
