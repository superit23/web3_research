from samson.core.base_object import BaseObject

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
