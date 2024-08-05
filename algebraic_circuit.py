class R1CSSystem(BaseObject):
    def __init__(self, constraints):
        self.constraints = constraints

    def is_valid_assignment(self, S: list):
        return all(con.is_valid_assignment(S) for con in self.constraints)


class R1CSConstraint(BaseObject):
    def __init__(self, ai, bi, ci):
        self.ai = ai
        self.bi = bi
        self.ci = ci

    def is_valid_assignment(self, S: list):
        A = sum([a*v for a,v in zip(self.ai, [1] + S)])
        B = sum([b*v for b,v in zip(self.bi, [1] + S)])
        C = sum([c*v for c,v in zip(self.ci, [1] + S)])

        return A * B == C


# Test example
F = ZZ/ZZ(13)
I = [F(11)]
W = [F(2), F(3), F(4), F(6)]


system = R1CSSystem([
    R1CSConstraint(
        [F(0), F(0), F(1), F(0), F(0), F(0)],
        [F(0), F(0), F(0), F(1), F(0), F(0)],
        [F(0), F(0), F(0), F(0), F(0), F(1)]
    ),
    R1CSConstraint(
        [F(0), F(0), F(0), F(0), F(0), F(1)],
        [F(0), F(0), F(0), F(0), F(1), F(0)],
        [F(0), F(1), F(0), F(0), F(0), F(0)]
    )
])

assert system.is_valid_assignment(I + W)


##########
# LABELS #
##########

class Label(BaseObject):
    def __init__(self, rep: str):
        self.rep = rep
    
    def __reprdir__(self):
        return ['rep']

    def is_constant(self):
        return False


class Constant(Label):
    def is_constant(self):
        return True



class EdgeLabelSystem(BaseObject):
    def __init__(self):
        self.labels = []
        self.ctr    = 1

    def generate(self):
        label = Label(f'S{self.ctr}')
        self.ctr += 1
        self.labels.append(label)
        return label

    def build_expression(self, *args):
        values = [0]*(len(self.labels)+1)
        for a in args:
            if a.is_constant():
                values[0] = a.value
            else:
                values[self[a]+1] = 1

        return R1CSExpression(values)
    

    def __getitem__(self, rep):
        if type(rep) is Label:
            return self.labels.index(rep)
        else:
            for l in self.labels:
                if l.rep == rep:
                    return l

        raise KeyError


    def build_solution_vector(self, sol: 'Dict[Label, FieldElement]'):
        values = [0]*len(self.labels)
        for label, value in sol.items():
            values[self[label]] = value

        return values


class R1CSExpression(BaseObject):
    def __init__(self, values: list):
        self.values = values
    
    def __add__(self, other: 'R1CSExpression'):
        return R1CSExpression([a+b for a,b, in zip(self.values, other.values)])

    def __mul__(self, value: int):
        return R1CSExpression([a*value for a, in self.values])


#########
# NODES #
#########

class Node(BaseObject):
    def __init__(self, label: Label, els: EdgeLabelSystem):
        self.label     = label
        self.els       = els
        self.in_nodes  = []
        self.out_nodes = []
        self.out_label = None
        self._value    = None

    def __reprdir__(self):
        return ['label', 'out_label']
    

    def __hash__(self):
        return hash((self.__class__, self.label, self.out_label, self._value))

    def is_labeled(self):
        return self.label is not None

    def add_in_edge(self, node: 'Node'):
        self.in_nodes.append(node)
        node.out_nodes.append(self)

    def add_out_edge(self, node: 'Node'):
        self.out_nodes.append(node)
        node.in_nodes.append(self)


    def try_generate_label(self):
        if len(self.in_nodes) == 2:
            l,r = self.in_nodes

            if l.out_label or r.out_label:
                if not self.out_label:
                    self.out_label = self.els.generate()


    def validate(self):
        assert len(self.in_nodes) == 2


    def finalize(self):
        if len(self.in_nodes):
            for node in self.in_nodes:
                node.finalize()

        self.validate()
        self.try_generate_label()


    def generate_constraint(self):
        self.finalize()
    

    def build_expression(self):
        self.finalize()
        if self.out_label:
            return self.els.build_expression(self.out_label)
        else:
            l,r = self.in_nodes
            if l.label.is_constant():
                if r.out_label:
                    return r.build_expression()*l.label.value


    @property
    def value(self):
        if self._value is None:
            self._value = self.execute()

        return self._value


class Source(Node):
    def validate(self):
        assert len(self.in_nodes) == 0

    def try_generate_label(self):
        if not self.label.is_constant():
            if not self.out_label:
                self.out_label = self.els.generate()


    @property
    def value(self):
        if self.label.is_constant():
            return self.label.value

        return self._value

    def set_value(self, value):
        self._value = value


class Sink(Node):
    def execute(self):
        return self.in_nodes[0].execute()

    def validate(self):
        assert len(self.in_nodes) == 1
        assert len(self.out_nodes) == 0


class ArithmeticGate(Node):
    pass

class AdditionGate(ArithmeticGate):
    def generate_constraint(self):
        self.finalize()
        l,r = self.in_nodes
        return R1CSConstraint(
            (l.build_expression() + r.build_expression()).values,
            self.els.build_expression(1).values,
            self.build_expression().values
        )

    def build_expression(self):
        self.finalize()
        if self.out_label:
            return self.els.build_expression(self.out_label)
        else:
            l,r = self.in_nodes
            if l.label.is_constant():
                # If l is constant, r must not be
                assert not r.label.is_constant()
                return r.build_expression() + self.els.build_expression(l.label.value)
            else:
                return l.build_expression() + self.els.build_expression(r.label.value)


    def execute(self):
        l,r = self.in_nodes
        return l.value + r.value


class MultiplicationGate(ArithmeticGate):
    def generate_constraint(self):
        self.finalize()
        l,r = self.in_nodes
        return R1CSConstraint(
            l.build_expression().values,
            r.build_expression().values,
            self.build_expression().values
        )

    def build_expression(self):
        self.finalize()
        if self.out_label:
            return self.els.build_expression(self.out_label)
        else:
            l,r = self.in_nodes
            if l.label.is_constant():
                # If l is constant, r must not be
                assert not r.label.is_constant()
                return r.build_expression() * l.label.value
            else:
                return l.build_expression() * r.label.value


    def execute(self):
        l,r = self.in_nodes
        return l.value * r.value


class AlgebraicCircuit(BaseObject):
    def __init__(self, nodes):
        self.nodes = nodes
    

    def __getitem__(self, name):
        for n in self.nodes:
            if n.label.rep == name:
                return n
        
        raise KeyError


    def execute(self):
        results = {}
        for n in self.nodes:
            if type(n) is Sink:
                n.execute()

        for n in self.nodes:
            if n.out_label:
                results[n.out_label] = n.value
        
        return results


    def build_r1cs_system(self):
        for node in self.nodes:
            node.finalize()

        constraints = []
        for node in self.nodes:
            constraint = node.generate_constraint()
            if constraint:
                constraints.append(constraint)
        
        return R1CSSystem(constraints)



els = EdgeLabelSystem()

x2, x1, x3, m1, m2, res = [
    Source(Label("x_2"), els),
    Source(Label("x_1"), els),
    Source(Label("x_3"), els),
    MultiplicationGate(Label("*"), els),
    MultiplicationGate(Label("*"), els),
    Sink(Label("f_(3.fac_zk)"), els)
]

circuit = AlgebraicCircuit([res, m2, x1, x2, x3, m1])

# Add edges
x2.add_out_edge(m1)
x1.add_out_edge(m1)
m1.add_out_edge(m2)
x3.add_out_edge(m2)
m2.add_out_edge(res)

r1cs = circuit.build_r1cs_system()

# Relabel for convenience
x1.out_label.rep = 'W1'
x2.out_label.rep = 'W2'
x3.out_label.rep = 'W3'
m1.out_label.rep = 'W4'
m2.out_label.rep = 'I1'

# Check to see if example works
S = els.build_solution_vector({els['W1']: F(2), els['W2']: F(3), els['W3']: F(4), els['W4']: F(6), els['I1']: F(11)})
assert r1cs.is_valid_assignment(S)

# Try custom trace
x1.set_value(F(7))
x2.set_value(F(3))
x3.set_value(F(2))

res = circuit.execute()
S   = els.build_solution_vector(res)
assert r1cs.is_valid_assignment(S)


class QAPSystem(BaseObject):
    def __init__(self, T, Ax, Bx, Cx):
        self.T  = T
        self.Ax = Ax
        self.Bx = Bx
        self.Cx = Cx


    @staticmethod
    def from_r1cs_system(F: 'Field', r1cs: R1CSSystem, m: 'List[FieldElement]'=None):
        # Set up some vars
        k     = len(r1cs.constraints)
        nm    = len(r1cs.constraints[0].ai)
        A,B,C = [[] for _ in range(nm)], [[] for _ in range(nm)], [[] for _ in range(nm)]

        Fm    = F.mul_group()
        G     = Fm.find_gen()
        m     = m or [G*j for j in range(1,k+1)]
        x     = Symbol('x')
        P     = F[x]
        T     = product([(x-ml) for ml in m])

        # Sort constraints into their polynomials
        for constraint in r1cs.constraints:
            for j, a in enumerate(constraint.ai):
                A[j].append(a)

            for j, b in enumerate(constraint.bi):
                B[j].append(b)

            for j, c in enumerate(constraint.ci):
                C[j].append(c)


        Ax, Bx, Cx = [[P.interpolate(list(zip(m, Xj))) for Xj in X] for X in (A, B, C)]
        return QAPSystem(T, Ax, Bx, Cx)


    def P(self, S):
        A = sum([a*v for a,v in zip(self.Ax, [1] + S)])
        B = sum([b*v for b,v in zip(self.Bx, [1] + S)])
        C = sum([c*v for c,v in zip(self.Cx, [1] + S)])

        return (A * B - C)
    

    def H(self, S):
        return self.P(S) // self.T

    def is_valid_assignment(self, S: list):
        return self.P(S) % self.T == self.T.ring(0)


qap = QAPSystem.from_r1cs_system(F, r1cs)

from copy import deepcopy

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



els = EdgeLabelSystem()

mul = Template('mul', els)
a   = mul.add(Input('a'))
b   = mul.add(Input('b'))
c   = mul.add(Output('c'))
m   = mul.add(MUL('m'))
m.set(a)
m.set(b)
c.set(m)


fac3 = Template('fac3', els)
x1   = fac3.add(Input('x1'))
x2   = fac3.add(Input('x2'))
x3   = fac3.add(Input('x3'))
x4   = fac3.add(Output('x4'))

mul1 = mul.instantiate('mul1', fac3)
mul2 = mul.instantiate('mul2', fac3)

mul1.a.set(x1)
mul1.b.set(x2)

mul2.a.set(mul1.c)
mul2.b.set(x3)
x4.set(mul2.c)

main = fac3.instantiate('main')


# Assert main connections
assert not main.x1.in_edges
assert not main.x2.in_edges
assert not main.x3.in_edges
assert not main.x4.out_edges

assert len(main.x1.out_edges) == 1 and main.x1.out_edges[0].resolve() == main.mul1.a
assert len(main.x2.out_edges) == 1 and main.x2.out_edges[0].resolve() == main.mul1.b
assert len(main.x2.out_edges) == 1 and main.x3.out_edges[0].resolve() == main.mul2.b
assert len(main.x4.in_edges) == 1 and main.x4.in_edges[0].resolve() == main.mul2.c

# Assert mul1 connections
assert len(main.mul1.a.in_edges) == 1 and main.mul1.a.in_edges[0].resolve() == main.x1
assert len(main.mul1.a.out_edges) == 1 and main.mul1.a.out_edges[0].resolve() == main.mul1.m

assert len(main.mul1.b.in_edges) == 1 and main.mul1.b.in_edges[0].resolve() == main.x2
assert len(main.mul1.b.out_edges) == 1 and main.mul1.b.out_edges[0].resolve() == main.mul1.m

assert len(main.mul1.m.in_edges) == 2 and main.mul1.m.in_edges[0].resolve() in (main.mul1.a, main.mul1.b) and main.mul1.m.in_edges[1].resolve() in (main.mul1.a, main.mul1.b)
assert len(main.mul1.m.out_edges) == 1 and main.mul1.m.out_edges[0].resolve() == main.mul1.c

assert len(main.mul1.c.in_edges) == 1 and main.mul1.c.in_edges[0].resolve() == main.mul1.m
assert len(main.mul1.c.out_edges) == 1 and main.mul1.c.out_edges[0].resolve() == main.mul2.a


# Assert mul2 connections
assert len(main.mul2.a.in_edges) == 1 and main.mul2.a.in_edges[0].resolve() == main.mul1.c
assert len(main.mul2.a.out_edges) == 1 and main.mul2.a.out_edges[0].resolve() == main.mul2.m

assert len(main.mul2.b.in_edges) == 1 and main.mul2.b.in_edges[0].resolve() == main.x3
assert len(main.mul2.b.out_edges) == 1 and main.mul2.b.out_edges[0].resolve() == main.mul2.m

assert len(main.mul2.m.in_edges) == 2 and main.mul2.m.in_edges[0].resolve() in (main.mul2.a, main.mul1.b) and main.mul2.m.in_edges[1].resolve() in (main.mul2.a, main.mul2.b)
assert len(main.mul2.m.out_edges) == 1 and main.mul2.m.out_edges[0].resolve() == main.mul2.c

assert len(main.mul2.c.in_edges) == 1 and main.mul2.c.in_edges[0].resolve() == main.mul2.m
assert len(main.mul2.c.out_edges) == 1 and main.mul2.c.out_edges[0].resolve() == main.x4


# Solve
circuit = main.build_circuit()
r1cs    = circuit.build_r1cs_system()

circuit['x1'].set_value(F(7))
circuit['x2'].set_value(F(3))
circuit['x3'].set_value(F(2))
res = circuit.execute()
S   = main.els.build_solution_vector(res)

assert r1cs.is_valid_assignment(S)


class Program(BaseObject):
    def __init__(self, context):
        self.templates  = {k:v for k,v in context.items() if type(v) is Template}
        self.components = {k:v for k,v in context.items() if type(v) is Component}
    
    def build(self, F: 'Field'):
        circuit = self.components['main'].build_circuit()
        r1cs    = circuit.build_r1cs_system()
        return circuit, QAPSystem.from_r1cs_system(F, r1cs)


import re
from enum import Enum, auto
NAME_RE           = r'([a-zA-Z0-9_\.]+)'
CALL_RE           = rf'{NAME_RE}[ ]*\(\)'

TEMPLATE_START_RE = re.compile(rf'template[ ]+{CALL_RE}')
INPUT_RE          = re.compile(rf'signal input {NAME_RE}')
OUTPUT_RE         = re.compile(rf'signal output {NAME_RE}')
ASSIGN_RE         = re.compile(r'([a-zA-Z0-9\.]+)[ ]*<==[ ]*(.*)')
CONSTRAIN_RE      = re.compile(r'([a-zA-Z0-9\.]+)[ ]*===[ ]*(.*)')
COMPONENT_RE      = re.compile(rf'component {NAME_RE} = {CALL_RE}')
MUL_RE            = re.compile(rf'{NAME_RE}[ ]*\*[ ]*{NAME_RE}')
ADD_RE            = re.compile(rf'{NAME_RE}[ ]*\+[ ]*{NAME_RE}')
VAR_RE            = re.compile(NAME_RE)

ALL_RE = [TEMPLATE_START_RE, INPUT_RE, OUTPUT_RE, ASSIGN_RE, COMPONENT_RE, MUL_RE]

class LexerState(Enum):
    ROOT         = auto()
    IN_COMPONENT = auto()
    IN_TEMPLATE  = auto()
    IN_SIGNAL    = auto()
    IN_ASSIGN    = auto()
    IN_OPERATOR  = auto()


class LexerFSM(BaseObject):
    ALLOWED_TRANSITIONS = {
        (LexerState.ROOT, LexerState.IN_COMPONENT),
        (LexerState.IN_TEMPLATE, LexerState.IN_COMPONENT),
        (LexerState.ROOT, LexerState.IN_TEMPLATE),
        (LexerState.IN_TEMPLATE, LexerState.IN_SIGNAL),
        (LexerState.IN_TEMPLATE, LexerState.IN_ASSIGN),
        (LexerState.IN_ASSIGN, LexerState.IN_OPERATOR),
    }

    def __init__(self):
        self.stack = [LexerState.ROOT]


    def push(self, next_state: LexerState):
        if (self.stack[-1], next_state) not in self.ALLOWED_TRANSITIONS:
            raise RuntimeError("Invalid state transition")
        
        self.stack.append(next_state)


    def pop(self):
        self.stack = self.stack[:-1]



class Lexer(BaseObject):
    def __init__(self):
        self.fsm = LexerFSM()


    def process_line(self, line: str, lines_left: 'List[str]', context: dict):
        for r in ALL_RE:
            match = r.match(line)
            if match:
                break

        if r == TEMPLATE_START_RE:
            return self.process_template(match, lines_left, context)
        elif r == INPUT_RE:
            return self.process_input(match, context), lines_left
        elif r == OUTPUT_RE:
            return self.process_output(match, context), lines_left
        elif r == VAR_RE:
            raise NotImplementedError
        elif r == ASSIGN_RE:
            return self.process_assign(match, context), lines_left
        elif r == MUL_RE:
            return self.process_mul(match, context), lines_left
        elif r == COMPONENT_RE:
            return self.process_component(match, context), lines_left


    def process_input(self, match, context):
        self.fsm.push(LexerState.IN_SIGNAL)
        name = match.groups()[0]
        node = Input(name)
        self.fsm.pop()

        context[name] = node
        context['parent'].add(node)
        return node


    def process_output(self, match, context):
        self.fsm.push(LexerState.IN_SIGNAL)
        name = match.groups()[0]
        node = Output(name)
        self.fsm.pop()

        context[name] = node
        context['parent'].add(node)
        return node


    def process_component(self, match, context):
        self.fsm.push(LexerState.IN_COMPONENT)
        name, com_type = match.groups()
        node           = context[com_type].instantiate(name, context['parent'])
        self.fsm.pop()

        context[name] = node
        return node


    def resolve_var(self, name, context):
        # Handle component assignment
        if '.' in name:
            com_name, path = name.split('.', 1)
            component = context[com_name]
            return component.namespace[path]
        else:
            return context[name]


    def process_assign(self, match, context):
        self.fsm.push(LexerState.IN_ASSIGN)

        lhs, rhs = match.groups()
    
        if MUL_RE.match(rhs):
            mul_node = self.process_mul(MUL_RE.match(rhs), context)
            self.resolve_var(lhs, context).set(mul_node)

        elif VAR_RE.match(rhs):
            v = VAR_RE.match(rhs).groups()[0]
            self.resolve_var(lhs, context).set(self.resolve_var(v, context))

        self.fsm.pop()


    def process_mul(self, match, context):
        self.fsm.push(LexerState.IN_OPERATOR)
        lhs, rhs = match.groups()
        node     = MUL(f'm_{random.randbytes(4).hex()}')
        context['parent'].add(node)

        node.set(self.resolve_var(lhs, context))
        node.set(self.resolve_var(rhs, context))
        self.fsm.pop()

        context[node.name] = node
        return node


    def process_template(self, match, lines_left, context):
        self.fsm.push(LexerState.IN_TEMPLATE)

        name         = match.groups()[0]
        node         = Template(name, context['els'])
        template_ctx = {'parent': node}

        template_ctx.update({k:v for k,v in context.items() if type(v) is (Template)})

        for i,line in enumerate(lines_left):
            if line == '}':
                break

            self.process_line(line, lines_left[i+1:], template_ctx)

        self.fsm.pop()
        context[name] = node
        return node, lines_left[i+1:]


    def lex(self, source: str):
        lines = [l.strip(' ;') for l in source.split('\n')]
        lines = [l for l in lines if l]

        els          = EdgeLabelSystem()
        root_context = {'parent': None, 'els': els}
        lines_left   = lines
        while lines_left:
            result, lines_left = self.process_line(lines_left[0], lines_left[1:], root_context)

        return Program(root_context)



source = """
template Multiplier() {
    signal input a ;
    signal input b ;
    signal output c ;
    c <== a*b ;
}

template three_fac() {
    signal input x1 ;
    signal input x2 ;
    signal input x3 ;
    signal output x4 ;
    component mult1 = Multiplier() ;
    component mult2 = Multiplier() ;
    mult1.a <== x1 ;
    mult1.b <== x2 ;
    mult2.a <== mult1.c ;
    mult2.b <== x3 ;
    x4 <== mult2.c ;
}

component main = three_fac()
"""

# Lexer -> ASG -> Algebraic Circuit -> R1CS -> QAP
l            = Lexer()
prog         = l.lex(source)
circuit, qap = prog.build(F)

# Check if circuit execution and QAP works
circuit['x1'].set_value(F(7))
circuit['x2'].set_value(F(3))
circuit['x3'].set_value(F(2))
res = circuit.execute()
S   = main.els.build_solution_vector(res)

assert qap.is_valid_assignment(S)


# Make sure it doesn't if the solution is wrong
S_bad    = [e for e in S]
S_bad[0] = F(1)
assert not qap.is_valid_assignment(S_bad)


# TODO
# ---------
# Add addition to ASG
# Add addition to Lexer
# Test Lexer against more complicated Circom programs
# Implement with BN-254 pairing group


library = """
template subtract() {
    signal input a ;
    signal input b ;
    signal output c ;
    c <== a+1*b ;
}
template check_inv() {
    signal input a ;
    signal input b ;
    a*b === 1 ;
}
template divide() {
    signal input a ;
    signal input b ;
    signal input b_inv ;
    signal output c ;
    component c_inv = check_inv() ;
    c_inv.a <== b
    c_inv.b <== b_inv
    c <== a*b_inv
}
template check_bool() {
    signal input a ;
    a*(1-a) === 0 ;
}
template conditional() {
    signal input a ;
    signal input b ;
    signal input switch ;
    signal output c ;
    component c_bool = check_bool() ;
    c <== a*switch + (1-switch)*b ;
}"""


# Compile 3fac problem into QAP
Fr = ZZ/ZZ(13)
I  = [Fr(11)]
W  = [Fr(2), Fr(3), Fr(4), Fr(6)]

system = R1CSSystem([
    R1CSConstraint(
        [Fr(0), Fr(0), Fr(1), Fr(0), Fr(0), Fr(0)],
        [Fr(0), Fr(0), Fr(0), Fr(1), Fr(0), Fr(0)],
        [Fr(0), Fr(0), Fr(0), Fr(0), Fr(0), Fr(1)]
    ),
    R1CSConstraint(
        [Fr(0), Fr(0), Fr(0), Fr(0), Fr(0), Fr(1)],
        [Fr(0), Fr(0), Fr(0), Fr(0), Fr(1), Fr(0)],
        [Fr(0), Fr(1), Fr(0), Fr(0), Fr(0), Fr(0)]
    )
])

qap = QAPSystem.from_r1cs_system(Fr, system, m=(Fr(5), Fr(7)))

# Use compiled QAP to generate zk-SNARK
n,m = len(I), len(W)
F   = ZZ/ZZ(43)
E   = EllipticCurve(F(0), F(6))

# Simulation trapdoor
ST = (int(Fr(6)), int(Fr(5)), int(Fr(4)), int(Fr(3)), int(Fr(2)))
alpha, beta, gamma, delta, tau = ST

# Build g1, g2 on the extension curve
y     = Symbol('y')
P     = F[y]
F43_6 = FF(43, 6, reducing_poly=y**6 + 6)

E6 = EllipticCurve(F43_6(E.a), F43_6(E.b))
g1 = E6(13, 15)
g2 = E6(7*y**2, 16*y**3)

# Calculate CRS
CRS_G1_0 = g1*alpha, g1*beta, g1*delta
CRS_G1_1 = [g1*(tau**j) for j in range(qap.T.degree())]
CRS_G1_2 = [g1*int((beta*qap.Ax[j](tau) + alpha*qap.Bx[j](tau) + qap.Cx[j](tau)) / gamma) for j in range(n+1)]
CRS_G1_3 = [g1*int((beta*qap.Ax[j+n](tau) + alpha*qap.Bx[j+n](tau) + qap.Cx[j+n](tau)) / delta) for j in range(1,m+1)]
CRS_G1_4 = [g1*int((tau**j * qap.T(tau)) / delta) for j in range(qap.T.degree()-1)]

CRS_G1 = (CRS_G1_0, CRS_G1_1, CRS_G1_2, CRS_G1_3, CRS_G1_4)
CRS_G2 = g2*beta, g2*gamma, g2*delta, [g2*int(tau**j) for j in range(qap.T.degree())]

# Prover
r,t = Fr(11), Fr(4) #[Fr.random() for _ in range(2)]
g1W = sum([g1P*int(w) for g1P, w in zip(CRS_G1_3, W)], E6.zero)
g1A = CRS_G1_0[0] + sum([g1*int(A(tau)*s) for A, s in zip(qap.Ax, ([0]+I+W))], E6.zero) + CRS_G1_0[-1]*int(r)
g1B = CRS_G1_0[1] + sum([g1*int(B(tau)*s) for B, s in zip(qap.Bx, ([0]+I+W))], E6.zero) + CRS_G1_0[-1]*int(t)
g2B = CRS_G2[0] + sum([g2*int(B(tau)*s) for B, s in zip(qap.Bx, ([0]+I+W))], E6.zero) + CRS_G2[2]*int(t)
g1C = g1W + g1*int((qap.H(I + W)(tau)*qap.T(tau))/delta) + g1A*int(t) + g1B*int(r) + CRS_G1_0[-1]*int(-r*t)

proof = (g1A, g1C, g2B)

assert g1A == E6(35, 15)
assert g1C == E6(13, 28)
assert g2B == E6(7*y**2, 27*y**3)



class Groth16Parameters(BaseObject):
    def __init__(self, G1, G2, g1, g2, Fr):
        self.G1 = G1
        self.G2 = G2
        self.g1 = g1
        self.g2 = g2
        self.Fr = Fr


class SimulationTrapdoor(BaseObject):
    def __init__(self, alpha, beta, gamma, delta, tau):
        self.alpha = int(alpha)
        self.beta  = int(beta)
        self.gamma = int(gamma)
        self.delta = int(delta)
        self.tau   = int(tau)
    

    @staticmethod
    def generate(Fr: 'Field') -> 'SimulationTrapdoor':
        Frm = Fr.mul_group()
        st  = set()
        
        while len(st) < 5:
            st.add(Frm.random())

        return SimulationTrapdoor(*list(st))



class CRS(BaseObject):
    def __init__(self, qap, CRS_G1, CRS_G2, params: 'Groth16Parameters'):
        self.qap    = qap
        self.CRS_G1 = CRS_G1
        self.CRS_G2 = CRS_G2
        self.params = params


    @staticmethod
    def generate(qap: QAPSystem, params: Groth16Parameters, st: SimulationTrapdoor, num_instances: int) -> 'CRS':
        g1, g2 = params.g1, params.g2
        n, m   = num_instances, len(qap.Ax)-num_instances-1

        CRS_G1_0 = g1*st.alpha, g1*st.beta, g1*st.delta
        CRS_G1_1 = [g1*(st.tau**j) for j in range(qap.T.degree())]
        CRS_G1_2 = [g1*int((st.beta*qap.Ax[j](st.tau) + st.alpha*qap.Bx[j](st.tau) + qap.Cx[j](st.tau)) / st.gamma) for j in range(n+1)]
        CRS_G1_3 = [g1*int((st.beta*qap.Ax[j+n](st.tau) + st.alpha*qap.Bx[j+n](st.tau) + qap.Cx[j+n](st.tau)) / st.delta) for j in range(1,m+1)]
        CRS_G1_4 = [g1*int((st.tau**j * qap.T(st.tau)) / st.delta) for j in range(qap.T.degree()-1)]

        CRS_G1 = (CRS_G1_0, CRS_G1_1, CRS_G1_2, CRS_G1_3, CRS_G1_4)
        CRS_G2 = g2*st.beta, g2*st.gamma, g2*st.delta, [g2*int(st.tau**j) for j in range(qap.T.degree())]

        return CRS(qap, CRS_G1, CRS_G2, params)


    def _eval_tau(self, P, pot):
        return sum([g_tau_j*int(coeff) for coeff, g_tau_j in zip(P, pot)], pot[0].ring.zero)

    def eval_g1_tau(self, P):
        return self._eval_tau(P, self.CRS_G1[1])

    def eval_g2_tau(self, P):
        return self._eval_tau(P, self.CRS_G2[3])

    def eval_gT_tau(self, P):
        return self._eval_tau(P, self.CRS_G1[4])


class Groth16Proof(BaseObject):
    def __init__(self, g1A, g1C, g2B, crs):
        self.g1A = g1A
        self.g1C = g1C
        self.g2B = g2B
        self.crs = crs


    @staticmethod
    def generate(crs: 'CRS', I: list, W: list, r: 'FieldElement'=None, t: 'FieldElement'=None) -> 'Groth16Proof':
        r = r or Fr.random()
        t = t or Fr.random()

        g1_alpha = crs.CRS_G1[0][0]
        g1_beta  = crs.CRS_G1[0][1]
        g1_delta = crs.CRS_G1[0][-1]

        g2_beta  = crs.CRS_G2[0]
        g2_delta = crs.CRS_G2[2]

        g1W = sum([g1P*int(w) for g1P, w in zip(crs.CRS_G1[3], W)], E6.zero)
        g1A = g1_alpha + sum([crs.eval_g1_tau(A)*int(s) for A, s in zip(crs.qap.Ax, ([0]+I+W))], E6.zero) + g1_delta*int(r)
        g1B = g1_beta  + sum([crs.eval_g1_tau(B)*int(s) for B, s in zip(crs.qap.Bx, ([0]+I+W))], E6.zero) + g1_delta*int(t)
        g2B = g2_beta  + sum([crs.eval_g2_tau(B)*int(s) for B, s in zip(crs.qap.Bx, ([0]+I+W))], E6.zero) + g2_delta*int(t)
        g1C = g1W + crs.eval_gT_tau(crs.qap.H(I + W)) + g1A*int(t) + g1B*int(r) + g1_delta*int(-r*t)

        return Groth16Proof(g1A, g1C, g2B, crs)
    

    def verify(self, I: list):
        g1_alpha = self.crs.CRS_G1[0][0]
        g1_beta  = self.crs.CRS_G1[0][1]
        g1_delta = self.crs.CRS_G1[0][-1]

        g2_beta  = self.crs.CRS_G2[0]
        g2_gamma = self.crs.CRS_G2[1]
        g2_delta = self.crs.CRS_G2[2]

        def e(g1, g2):
            return g1.weil_pairing(g2, g1.order())

        g1_I = sum([g1_g*int(i) for g1_g, i in zip(self.crs.CRS_G1[2], [0]+I)], self.crs.params.G2.zero)

        return e(self.g1A, self.g2B) == e(g1_alpha, g2_beta) * e(g1_I, g2_gamma) * e(self.g1C, g2_delta)


# Compile 3fac problem into QAP
Fr = ZZ/ZZ(13)
I  = [Fr(11)]
W  = [Fr(2), Fr(3), Fr(4), Fr(6)]

system = R1CSSystem([
    R1CSConstraint(
        [Fr(0), Fr(0), Fr(1), Fr(0), Fr(0), Fr(0)],
        [Fr(0), Fr(0), Fr(0), Fr(1), Fr(0), Fr(0)],
        [Fr(0), Fr(0), Fr(0), Fr(0), Fr(0), Fr(1)]
    ),
    R1CSConstraint(
        [Fr(0), Fr(0), Fr(0), Fr(0), Fr(0), Fr(1)],
        [Fr(0), Fr(0), Fr(0), Fr(0), Fr(1), Fr(0)],
        [Fr(0), Fr(1), Fr(0), Fr(0), Fr(0), Fr(0)]
    )
])

qap = QAPSystem.from_r1cs_system(Fr, system, m=(Fr(5), Fr(7)))
st  = SimulationTrapdoor(Fr(6), Fr(5), Fr(4), Fr(3), Fr(2))

# Build curves
F   = ZZ/ZZ(43)
E   = EllipticCurve(F(0), F(6))

y     = Symbol('y')
P     = F[y]
F43_6 = FF(43, 6, reducing_poly=y**6 + 6)

E6 = EllipticCurve(F43_6(E.a), F43_6(E.b))
g1 = E6(13, 15)
g2 = E6(7*y**2, 16*y**3)

params = Groth16Parameters(G1=E, G2=E6, g1=g1, g2=g2, Fr=Fr)
crs    = CRS.generate(qap, params, st, num_instances=len(I))
proof  = Groth16Proof.generate(crs, I, W, r=Fr(11), t=Fr(4))

assert proof.g1A == E6(35, 15)
assert proof.g1C == E6(13, 28)
assert proof.g2B == E6(7*y**2, 27*y**3)

assert proof.verify(I)
assert not proof.verify([Fr(3)])


# ALTOGETHER!

# Lexer -> ASG -> Algebraic Circuit -> R1CS -> QAP
l            = Lexer()
prog         = l.lex(source)
circuit, qap = prog.build(Fr)

# Check if circuit execution and QAP works
circuit['x1'].set_value(Fr(7))
circuit['x2'].set_value(Fr(3))
circuit['x3'].set_value(Fr(2))
res = circuit.execute()
S   = main.els.build_solution_vector(res)

I, W = S[:1], S[1:]

# Build SNARK
st  = SimulationTrapdoor(Fr(6), Fr(5), Fr(4), Fr(3), Fr(2))
F   = ZZ/ZZ(43)
E   = EllipticCurve(F(0), F(6))

y     = Symbol('y')
P     = F[y]
F43_6 = FF(43, 6, reducing_poly=y**6 + 6)

E6 = EllipticCurve(F43_6(E.a), F43_6(E.b))
g1 = E6(13, 15)
g2 = E6(7*y**2, 16*y**3)

params = Groth16Parameters(G1=E, G2=E6, g1=g1, g2=g2, Fr=Fr)
crs    = CRS.generate(qap, params, st, num_instances=len(I))
proof  = Groth16Proof.generate(crs, I, W, r=Fr(11), t=Fr(4))

assert proof.verify(I)
assert not proof.verify([Fr(3)])
