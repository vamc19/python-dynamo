import socket
from collections import defaultdict
from hashlib import md5
import bisect


class Ring(object):

    def __init__(self, vnode_count=1, replica_count=0):
        """Create a new Ring.

        :param vnode_count: number of virtual nodes.
        :param replica_count: number of replicas for each key
        """

        self.vnode_count = 1  # for now, only 1 vnode is supported
        self.replica_count = replica_count

        # maps node_id to corresponding virtual nodes (stored as set)
        self._vnode_mapping = defaultdict(set)

        self._vnode_hashes = []
        self._nodes = {}

        self.ip_to_hostname = {}
        self.hostname_to_ip = {}

        self._generate_hash = lambda key: int(md5(key.encode('utf-8')).hexdigest(), 16)
        self._generate_vnode_ids = lambda node_id: (node_id + '_' + str(i) for i in range(self.vnode_count))

    def __setitem__(self, node_id, hostname):
        """Add a node (and virtual nodes), given its id and hostname"""
        for vnode_id in self._generate_vnode_ids(node_id):
            vnode_hash = self._generate_hash(vnode_id)

            if vnode_hash in self._nodes:
                raise ValueError("Node id %r is already present" % vnode_id)
            self._nodes[vnode_hash] = hostname
            bisect.insort(self._vnode_hashes, vnode_hash)

            self._vnode_mapping[node_id].add(vnode_hash)

    def __delitem__(self, node_id):
        """Remove a node, given its id."""

        vnode_hashes = self._vnode_mapping.get(node_id, None)
        if not vnode_hashes:
            raise ValueError("Node id not in the ring" % node_id)

        for vnode_hash in vnode_hashes:
            del self._nodes[vnode_hash]
            index = bisect.bisect_left(self._vnode_hashes, vnode_hash)
            del self._vnode_hashes[index]

    def _get_nearest_hash_index(self, key_hash):
        """Given a hash value, returns the index of nearest hash in _vnode_hashes."""

        nearest_hash_index = bisect.bisect(self._vnode_hashes, key_hash)
        if nearest_hash_index == len(self._vnode_hashes):
            return 0

        return nearest_hash_index

    def __getitem__(self, key):
        """Return a node hostname, given a key.

        The vnode with a hash value nearest but not less than that of the given
        key is returned. If the hash of the given name is greater than the greatest
        hash, returns the lowest hashed node.

        """
        key_hash = self._generate_hash(key)
        hash_index = self._get_nearest_hash_index(key_hash)
        return self._nodes[self._vnode_hashes[hash_index]]

    def __len__(self):
        return len(self._nodes) // self.vnode_count  # to account for vnode_count

    def __contains__(self, node_id):
        vnode_ids = list(self._generate_vnode_ids(node_id))

        return self._generate_hash(vnode_ids[0]) in self._nodes

    # Helper functions to expose stable API
    def add_node(self, node_hostname):
        ip = socket.gethostbyname(node_hostname)
        self.ip_to_hostname[ip] = node_hostname
        self.hostname_to_ip[node_hostname] = ip
        return self.__setitem__(node_hostname, node_hostname)

    def remove_node(self, node_hostname):
        ip = self.hostname_to_ip[node_hostname]
        del self.ip_to_hostname[ip]
        del self.hostname_to_ip[node_hostname]
        return self.__delitem__(node_hostname)

    def get_node_for_key(self, key):
        return self.__getitem__(key)

    def get_replicas_for_key(self, key):
        key_hash = self._generate_hash(key)
        hash_index = self._get_nearest_hash_index(key_hash)

        replica_list = []  # Only contains replicas, not the main node. len = self.replica_count
        for x in range(hash_index + 1, hash_index + self.replica_count + 1):
            index = x % len(self._vnode_hashes)  # wrap around the list
            replica_list.append(self._nodes[self._vnode_hashes[index]])

        return replica_list

    def get_all_hosts(self):
        return set(self._nodes.values())

    def get_handoff_node(self, node_ip):
        hostname = self.ip_to_hostname[node_ip]
        # hostname = node_ip
        vnode_ids = list(self._generate_vnode_ids(hostname))

        index = self._get_nearest_hash_index(self._generate_hash(vnode_ids[0]))
        handoff_index = (index + self.replica_count) % len(self._vnode_hashes)

        return self._nodes[self._vnode_hashes[handoff_index]]

    def get_key_range(self, hostname):
        vnode_id = list(self._generate_vnode_ids(hostname))[0]
        index = self._get_nearest_hash_index(self._generate_hash(vnode_id))

        start_key = self._vnode_hashes[index-2]
        end_key = self._vnode_hashes[index-1]

        return start_key, end_key


if __name__ == '__main__':
    # to make these cases work, comment lines 86-88, 115. Uncomment 116.

    r = Ring(vnode_count=1, replica_count=3)

    r.add_node("node1.hostname")
    r.add_node("node2.hostname")
    r.add_node("node3.hostname")
    r.add_node("node4.hostname")
    r.add_node("node5.hostname")
    r.add_node("node6.hostname")
    r.add_node("node7.hostname")

    # print node arrangement:
    print("ring structure:")
    sids = sorted(r._vnode_hashes)
    for s in sids:
        print(s, r._nodes[s])
    print('\n')

    print("range for node1:", r.get_key_range("node1.hostname"))
    print("range for node2:", r.get_key_range("node2.hostname"))
    print("range for node3:", r.get_key_range("node3.hostname"))
    print("range for node4:", r.get_key_range("node4.hostname"))
    print("range for node5:", r.get_key_range("node5.hostname"))
    print("range for node6:", r.get_key_range("node6.hostname"))
    print("range for node7:", r.get_key_range("node7.hostname"))

    # # Try inserting a key
    # print("for key1...")
    # target_hostname = r.get_node_for_key("key1")
    # key_hash = r._generate_hash("key1")
    # print(key_hash, target_hostname)  # got node2hostname
    # # proceed to put data in target_hostname
    #
    # print("\nfor key2..")
    #
    # target_hostname = r.get_node_for_key("key2")
    # key_hash = r._generate_hash("key2")
    # print(key_hash, target_hostname)  # got node3hostname
    #
    # print("\nfor key6..")
    #
    # target_hostname = r.get_node_for_key("key6")
    # key_hash = r._generate_hash("key6")
    # print(key_hash, target_hostname)  # got node3hostname
    #
    #
    # print("\nfor key10..")
    #
    # target_hostname = r.get_node_for_key("key10")
    # key_hash = r._generate_hash("key10")
    #
    # print(key_hash, target_hostname)  # got node3hostname
    #
    # print("\nfor key11..")
    #
    # target_hostname = r.get_node_for_key("key11")
    # key_hash = r._generate_hash("key11")
    #
    # print(key_hash, target_hostname)  # got node3hostname
    #
    # print(len(r))
    #
    # # print(r.get_all_hosts())
    #
    # print("node1.hostname" in r)
    # print("node100" in r)
    # print("node3" in r)

    print(r.get_all_hosts())

    r.remove_node("node1.hostname")
    print(r.get_all_hosts())

    # print node arrangement:
    print("ring structure:")
    sids = sorted(r._vnode_hashes)
    for s in sids:
        print(s, r._nodes[s])
    print('\n\n\n')

    # print(r.get_handoff_node("node1.hostname"))
