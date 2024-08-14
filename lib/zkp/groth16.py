from samson.core.base_object import BaseObject

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
    def generate(qap: 'QAPSystem', params: Groth16Parameters, st: SimulationTrapdoor, num_instances: int) -> 'CRS':
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
        Frm = crs.params.Fr.mul_group()
        r   = r or Frm.random().val
        t   = t or Frm.random().val

        g1_alpha = crs.CRS_G1[0][0]
        g1_beta  = crs.CRS_G1[0][1]
        g1_delta = crs.CRS_G1[0][-1]

        g2_beta  = crs.CRS_G2[0]
        g2_delta = crs.CRS_G2[2]
        zero     = g1_alpha.ring.zero

        g1W = sum([g1P*int(w) for g1P, w in zip(crs.CRS_G1[3], W)], zero)
        g1A = g1_alpha + sum([crs.eval_g1_tau(A)*int(s) for A, s in zip(crs.qap.Ax, ([0]+I+W))], zero) + g1_delta*int(r)
        g1B = g1_beta  + sum([crs.eval_g1_tau(B)*int(s) for B, s in zip(crs.qap.Bx, ([0]+I+W))], zero) + g1_delta*int(t)
        g2B = g2_beta  + sum([crs.eval_g2_tau(B)*int(s) for B, s in zip(crs.qap.Bx, ([0]+I+W))], zero) + g2_delta*int(t)
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


    @staticmethod
    def forge(crs: 'CRS', I: list, st: "SimulationTrapdoor", A: 'FieldElement'=None, B: 'FieldElement'=None):
        Frm = crs.params.Fr.mul_group()
        A,B = A or Frm.random().val, B or Frm.random().val
        g1  = crs.params.g1
        g2  = crs.params.g2
        g1A = g1*int(A)
        g2B = g2*int(B)

        I_prime = [1, *I]
        g1C     = g1*int(A*B / st.delta) + g1*int(-st.alpha*st.beta / st.delta) + sum([g1*int(-(st.beta*crs.qap.Ax[j](st.tau) + st.alpha*crs.qap.Bx[j](st.tau) + crs.qap.Cx[j](st.tau)) / st.delta * I_prime[j]) for j in range(len(I_prime))], g1.ring.zero)

        return Groth16Proof(g1A, g1C, g2B, crs)
