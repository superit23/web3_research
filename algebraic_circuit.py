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


    def build_solution_vector(self, sol: dict):
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
    def __init__(self, label: Label, system: EdgeLabelSystem):
        self.label     = label
        self.system    = system
        self.in_nodes  = []
        self.out_nodes = []
        self.out_label = None

    def __reprdir__(self):
        return ['label', 'out_label']

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
                    self.out_label = self.system.generate()


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
            return self.system.build_expression(self.out_label)
        else:
            l,r = self.in_nodes
            if l.label.is_constant():
                if r.out_label:
                    return r.build_expression()*l.label.value


class Source(Node):
    def validate(self):
        assert len(self.in_nodes) == 0

    def try_generate_label(self):
        if not self.label.is_constant():
            if not self.out_label:
                self.out_label = self.system.generate()



class Sink(Node):
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
            self.system.build_expression(1).values,
            self.build_expression().values
        )

    def build_expression(self):
        self.finalize()
        if self.out_label:
            return self.system.build_expression(self.out_label)
        else:
            l,r = self.in_nodes
            if l.label.is_constant():
                # If l is constant, r must not be
                assert not r.label.is_constant()
                return r.build_expression() + self.system.build_expression(l.label.value)
            else:
                return l.build_expression() + self.system.build_expression(r.label.value)


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
            return self.system.build_expression(self.out_label)
        else:
            l,r = self.in_nodes
            if l.label.is_constant():
                # If l is constant, r must not be
                assert not r.label.is_constant()
                return r.build_expression() * l.label.value
            else:
                return l.build_expression() * r.label.value



class AlgebraicCircuit(BaseObject):
    def __init__(self, nodes):
        self.nodes  = nodes

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

# Check to see if it works
S = els.build_solution_vector({els['W1']: F(2), els['W2']: F(3), els['W3']: F(4), els['W4']: F(6), els['I1']: F(11)})
assert r1cs.is_valid_assignment(S)
