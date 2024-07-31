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
    def from_r1cs_system(F: 'Field', r1cs: R1CSSystem):
        # Set up some vars
        k     = len(r1cs.constraints)
        nm    = len(r1cs.constraints[0].ai)
        A,B,C = [[] for _ in range(nm)], [[] for _ in range(nm)], [[] for _ in range(nm)]

        Fm    = F.mul_group()
        G     = Fm.find_gen()
        m     = [G*j for j in range(1,k+1)]
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


    def is_valid_assignment(self, S: list):
        A = sum([a*v for a,v in zip(self.Ax, [1] + S)])
        B = sum([b*v for b,v in zip(self.Bx, [1] + S)])
        C = sum([c*v for c,v in zip(self.Cx, [1] + S)])

        return (A * B - C) % self.T == P(0)


qap = QAPSystem.from_r1cs_system(F, r1cs)

from copy import deepcopy

class Reference(BaseObject):
    def __init__(self, namespace, name):
        self.namespace = namespace
        self.name      = name
    
    def resolve(self):
        return self.namespace[self.name]


class Namespace(BaseObject):
    def __init__(self, name: str):
        self.name    = name
        self.objects = {}
    

    def __reprdir__(self):
        return ['name']

    
    def ref(self, name):
        return Reference(self, name)


    def __getattr__(self, name):
        try:
            return object.__getattr__(self, name)
        except AttributeError as e:
            try:
                return self.objects[name]
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
    

    def copy(self, namespace):
        new_obj = Namespace(self.name)
        for k,v in self.objects.items():
            new_obj[k] = v.copy(new_obj)
        
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
    

    def copy(self, namespace):
        new_obj = self.__class__(name=self.name, els=self.els)
        new_obj.in_edges  = [namespace.ref(e.name) for e in self.in_edges]
        new_obj.out_edges = [namespace.ref(e.name) for e in self.out_edges]
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

                if out_node not in node.out_nodes:
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


class Template(BaseObject):
    def __init__(self, name=None, els=None):
        self.name      = name
        self.els       = els
        self.namespace = Namespace(name)


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
        els       = parent.els if parent else self.els
        component = Component(name=name, els=els)

        for k,v in self.namespace.objects.items():
            new_obj                = v.copy(component.namespace)
            new_obj.parent         = component
            component.namespace[k] = new_obj

        if parent:
            parent.namespace[name] = component
        
        return component


class Component(BaseObject):
    def __init__(self, name=None, els=None, namespace=None):
        self.name      = name
        self.els       = els
        self.namespace = namespace or Namespace(name)


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
        return nodes
    

    def build_circuit(self):
        return AlgebraicCircuit(self._flatten())
    

    def copy(self, namespace):
        new_obj = self.__class__(name=self.name, els=self.els, namespace=self.namespace.copy(namespace))
        return new_obj


class MUL(ASTObject):
    def force_build(self):
        assert len(self.in_edges) == 2

        node = MultiplicationGate(Label("*"), self.els)
        self._last_built = node

        in_l, in_r = [e.resolve().build() for e in self.in_edges]

        if in_l not in node.in_nodes:
            node.add_in_edge(in_l)
        
        if in_r not in node.in_nodes:
            node.add_in_edge(in_r)

        for out_edge in self.out_edges:
            out_node = out_edge.resolve().build()

            if out_node not in node.out_nodes:
                node.add_out_edge(out_node)

        return node


els = EdgeLabelSystem()

mul = Template('mul', els)
a   = mul.add(Input('a'))
b   = mul.add(Input('b'))
c   = mul.add(Output('c'))
m   = mul.add(MUL('*1'))
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



# Solve
# circuit = C.build_circuit()
# r1cs    = circuit.build_r1cs_system()

# x1.set_value(F(7))
# x2.set_value(F(3))
# x3.set_value(F(2))
# res = circuit.execute()
# S   = C.els.build_solution_vector(res)


"""
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
