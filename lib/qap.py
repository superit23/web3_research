from samson.core.base_object import BaseObject
from samson.math.symbols import Symbol
from samson.math.general import product

class QAPSystem(BaseObject):
    def __init__(self, T, Ax, Bx, Cx):
        self.T  = T
        self.Ax = Ax
        self.Bx = Bx
        self.Cx = Cx


    @staticmethod
    def from_r1cs_system(F: 'Field', r1cs: 'R1CSSystem', m: 'List[FieldElement]'=None):
        # Set up some vars
        k     = len(r1cs.constraints)
        nm    = len(r1cs.constraints[0].ai)
        A,B,C = [[] for _ in range(nm)], [[] for _ in range(nm)], [[] for _ in range(nm)]

        Fm    = F.mul_group()
        m     = m or [Fm.random().val for _ in range(1,k+1)]
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

