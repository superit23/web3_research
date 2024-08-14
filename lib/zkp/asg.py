
from copy import deepcopy
from samson.core.base_object import BaseObject
from algebraic_circuit import MultiplicationGate, AdditionGate, EdgeLabelSystem, Source, Sink, Label, AlgebraicCircuit

class Reference(BaseObject):
    def __init__(self, namespace, name):
        self.namespace = namespace
        self.name      = name
    
    def resolve(self):
        containing_ns = self.namespace.get_namespace_by_rns(self.name.rsplit('.', 1)[0])
        return containing_ns[self.name.rsplit('.', 1)[1]]


class Namespace(BaseObject):
    def __init__(self, name: str, parent=None):
        self.name     = name
        self.objects  = {}
        self.children = {}
        self.parent   = parent
    

    def create_or_get_childspace(self, name):
        if not name in self.children:
            namespace = Namespace(name, self)
            self.children[name] = namespace

        return self.children[name]


    def get_fqns(self):
        if self.parent:
            return f'{self.parent.get_fqns()}.{self.name}'
        else:
            return self.name


    def get_namespace_by_rns(self, rns: str, force_create: bool=False):
        """
        Traverses the namespace tree by its relative name.
        """
        fqns = self.get_fqns()

        # RNS is a FQNS and matches us
        # fqns: 'main.mul.doit'
        # rns:  'main.mul.doit'
        if fqns == rns:
            return self
        
        # The RNS refers to a lower FQNS
        # fqns: 'main.mul'
        # rns:  'main.mul.doit'
        elif rns.startswith(fqns):
            child_space = rns.split(fqns)[1].strip('.')
            try:
                return self.children[child_space]
            except KeyError as e:
                if force_create:
                    return self.create_or_get_childspace(child_space)

                raise e
        

        # The RNS refers to a lower relative namespace
        # fqns: 'main'
        # rns:  'mul'
        elif rns in self.children:
            return self.children[rns]

        # The RNS refers to a higher namespace or different namespace on the same level
        # fqns: 'main.mul.doit'
        # rns:  'main.mul'

        # fqns: 'main.mul.doit1'
        # rns:  'main.mul.doit2'
        elif self.parent:
            return self.parent.get_namespace_by_rns(rns, force_create)

        elif force_create:
            return self.create_or_get_childspace(rns)

        raise RuntimeError("Cannot traverse further; no higher parent")



    def __reprdir__(self):
        return ['name']

    
    def ref(self, name):
        return Reference(self, f'{self.get_fqns()}.{name}')


    def __getattr__(self, name):
        try:
            return object.__getattr__(self, name)
        except AttributeError as e:
            try:
                return self.children[name]
            except KeyError:
                try:
                    return self.objects[name]
                except KeyError:
                    raise e


    def __getitem__(self, name):
        parts = name.split('.', 1)
        if len(parts) == 1:
            curr_part, next_part = parts[0], ""
        else:
            curr_part, next_part = parts

        curr = self.objects[curr_part]
        if next_part:
            return getattr(curr, next_part)
        else:
            return curr


    def __setitem__(self, name, value):
        parts = name.split('.', 1)
        if len(parts) == 1:
            curr_part, next_part = parts[0], ""
        else:
            curr_part, next_part = parts

        if next_part:
            self.objects[curr_part][next_part] = value
        else:
            self.objects[curr_part] = value
    

    def copy(self, parent, namespace, ns_translation):
        new_obj = namespace.create_or_get_childspace(self.name)
        for k,v in self.objects.items():
            new_obj[k] = v.copy(parent, new_obj, ns_translation)
        
        return new_obj



class ASTObject(BaseObject):
    def __init__(self, name, els=None):
        self.name        = name
        self.els         = els
        self.in_edges    = []
        self.out_edges   = []
        self.parent      = None
        self._last_built = None


    def __reprdir__(self):
        return ['name']


    def set(self, other: 'ASTObject'):
        self.in_edges.append(other.parent.namespace.ref(other.name))
        other.out_edges.append(self.parent.namespace.ref(self.name))
    

    def build(self):
        if not self._last_built:
            self._last_built = self.force_build()
        
        return self._last_built


    def clear_build(self):
        self._last_built = None


    def copy(self, parent, namespace, ns_translation):
        new_obj = self.__class__(name=self.name, els=self.els)

        def translate_edges(edges):
            new_edges = []
            for ref in edges:
                # Translate FQNS
                new_parts = []
                for part in ref.name.split('.')[:-1]:
                    new_parts.append(ns_translation.get(part, part))
                
                # Recreate in new namespace tree
                new_fqns = '.'.join(new_parts)
                ref_ns   = namespace.get_namespace_by_rns(new_fqns, force_create=True)
                new_ref  = ref_ns.ref(ref.name.split('.')[-1])
                new_edges.append(new_ref)

            return new_edges

        new_obj.in_edges  = translate_edges(self.in_edges)
        new_obj.out_edges = translate_edges(self.out_edges)
        new_obj.parent    = parent
        return new_obj


class Input(ASTObject):
    def force_build(self):
        # If wired from another component, can only have ONE incoming
        # Otherwise, zero
        assert len(self.in_edges) < 2
        if self.in_edges:
            return self.in_edges[0].resolve().build()
        else:
            node = Source(Label(self.name), self.els)
            self._last_built = node

            for out_edge in self.out_edges:
                out_node = out_edge.resolve().build()

                if out_node != node and out_node not in node.out_nodes:
                    node.add_out_edge(out_node)

            return node


class Output(ASTObject):
    def force_build(self):
        assert len(self.in_edges) == 1
        if self.out_edges:
            return self.in_edges[0].resolve().build()
        else:
            node = Sink(Label(self.name), self.els)
            self._last_built = node

            in_node = self.in_edges[0].resolve().build()
            if in_node not in node.in_nodes:
                node.add_in_edge(in_node)

            return node


class BinaryOperator(ASTObject):
    GATE  = None
    LABEL = None

    def force_build(self):
        assert len(self.in_edges) == 2

        node = self.GATE(Label(self.LABEL), self.els)
        self._last_built = node

        in_l, in_r = [e.resolve().build() for e in self.in_edges]

        if in_l not in node.in_nodes:
            node.add_in_edge(in_l)
        
        if in_r not in node.in_nodes:
            node.add_in_edge(in_r)

        for out_edge in self.out_edges:
            out_node = out_edge.resolve().build()

            if out_node != node and out_node not in node.out_nodes:
                node.add_out_edge(out_node)

        return node


class MUL(BinaryOperator):
    GATE  = MultiplicationGate
    LABEL = "*"

class ADD(BinaryOperator):
    GATE  = AdditionGate
    LABEL = "+"


class Template(BaseObject):
    def __init__(self, name=None, els=None):
        self.name      = name
        self.els       = els
        self.namespace = Namespace(name)
        self.parent    = None


    def __getattr__(self, name):
        try:
            return object.__getattr__(self, name)
        except AttributeError as e:
            try:
                return self.namespace[name]
            except KeyError:
                raise e


    def add(self, obj):
        obj.els    = self.els
        obj.parent = self
        self.namespace[obj.name] = obj
        return obj


    def instantiate(self, name, parent=None):
        els = parent.els if parent else self.els

        # Create a child namespace if we have a parent
        if parent:
            namespace = parent.namespace.create_or_get_childspace(name)
        else:
            namespace = Namespace(name)

        component      = Component(name=name, els=els, namespace=namespace, parent=parent)
        ns_translation = {self.namespace.name: name}

        if parent:
            parent.namespace[name] = component

        # Do components first to prevent dependency issues
        for k,v in self.namespace.objects.items():
            if v.is_a(Component):
                new_obj                = v.copy(component, component.namespace, ns_translation)
                component.namespace[k] = new_obj

        for k,v in self.namespace.objects.items():
            if not v.is_a(Component):
                new_obj                = v.copy(component, component.namespace, ns_translation)
                component.namespace[k] = new_obj

        return component


class Component(BaseObject):
    def __init__(self, name=None, els=None, namespace=None, parent=None):
        self.name      = name
        self.els       = els
        self.namespace = namespace
        self.parent    = parent


    def __getattr__(self, name):
        try:
            return object.__getattr__(self, name)
        except AttributeError as e:
            try:
                return self.namespace[name]
            except KeyError:
                raise e


    def _flatten(self):
        nodes = []
        for v in self.namespace.objects.values():
            if type(v) is Component:
                nodes.extend(v._flatten())
            else:
                nodes.append(v.build())
        return list(set(nodes))


    def build_circuit(self):
        return AlgebraicCircuit(self._flatten())


    def copy(self, parent, namespace, ns_translation):
        new_obj              = self.__class__(name=self.name, els=self.els)
        namespace[self.name] = self
        new_obj.parent       = parent
        new_obj.namespace    = self.namespace.copy(new_obj, namespace, ns_translation)
        return new_obj
