from samson.core.base_object import BaseObject
from r1cs import R1CSSystem, R1CSConstraint

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
