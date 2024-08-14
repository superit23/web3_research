from unittest import TestCase
from samson.all import *
from algebraic_circuit import MultiplicationGate, EdgeLabelSystem, Source, Sink, Label, AlgebraicCircuit
from asg import Template, Component, Input, Output, ADD, MUL
from groth16 import Groth16Proof, CRS, Groth16Parameters, SimulationTrapdoor
from lexer import Lexer
from qap import QAPSystem
from r1cs import R1CSSystem, R1CSConstraint


SOURCE_3FAC = """
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


class Web3TestCases(TestCase):
    def test_3fac_r1cs(self):
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

        self.assertTrue(system.is_valid_assignment(I + W))


    def test_3fac_qap(self):
        # Test example
        F = ZZ/ZZ(13)
        I = [F(11)]
        W = [F(2), F(3), F(4), F(6)]

        r1cs = R1CSSystem([
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

        qap = QAPSystem.from_r1cs_system(F, r1cs)
        self.assertTrue(qap.is_valid_assignment(I + W))


    def test_circuit(self):
        F   = ZZ/ZZ(13)
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
        self.assertTrue(r1cs.is_valid_assignment(S))

        # Try custom trace
        x1.set_value(F(7))
        x2.set_value(F(3))
        x3.set_value(F(2))

        res = circuit.execute()
        S   = els.build_solution_vector(res)
        self.assertTrue(r1cs.is_valid_assignment(S))



    def test_3fac_asg(self):
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
        self.assertTrue(not main.x1.in_edges)
        self.assertTrue(not main.x2.in_edges)
        self.assertTrue(not main.x3.in_edges)
        self.assertTrue(not main.x4.out_edges)

        self.assertTrue(len(main.x1.out_edges) == 1 and main.x1.out_edges[0].resolve() == main.mul1.a)
        self.assertTrue(len(main.x2.out_edges) == 1 and main.x2.out_edges[0].resolve() == main.mul1.b)
        self.assertTrue(len(main.x2.out_edges) == 1 and main.x3.out_edges[0].resolve() == main.mul2.b)
        self.assertTrue(len(main.x4.in_edges) == 1 and main.x4.in_edges[0].resolve() == main.mul2.c)

        # Assert mul1 connections
        self.assertTrue(len(main.mul1.a.in_edges) == 1 and main.mul1.a.in_edges[0].resolve() == main.x1)
        self.assertTrue(len(main.mul1.a.out_edges) == 1 and main.mul1.a.out_edges[0].resolve() == main.mul1.m)

        self.assertTrue(len(main.mul1.b.in_edges) == 1 and main.mul1.b.in_edges[0].resolve() == main.x2)
        self.assertTrue(len(main.mul1.b.out_edges) == 1 and main.mul1.b.out_edges[0].resolve() == main.mul1.m)

        self.assertTrue(len(main.mul1.m.in_edges) == 2 and main.mul1.m.in_edges[0].resolve() in (main.mul1.a, main.mul1.b) and main.mul1.m.in_edges[1].resolve() in (main.mul1.a, main.mul1.b))
        self.assertTrue(len(main.mul1.m.out_edges) == 1 and main.mul1.m.out_edges[0].resolve() == main.mul1.c)

        self.assertTrue(len(main.mul1.c.in_edges) == 1 and main.mul1.c.in_edges[0].resolve() == main.mul1.m)
        self.assertTrue(len(main.mul1.c.out_edges) == 1 and main.mul1.c.out_edges[0].resolve() == main.mul2.a)


        # Assert mul2 connections
        self.assertTrue(len(main.mul2.a.in_edges) == 1 and main.mul2.a.in_edges[0].resolve() == main.mul1.c)
        self.assertTrue(len(main.mul2.a.out_edges) == 1 and main.mul2.a.out_edges[0].resolve() == main.mul2.m)

        self.assertTrue(len(main.mul2.b.in_edges) == 1 and main.mul2.b.in_edges[0].resolve() == main.x3)
        self.assertTrue(len(main.mul2.b.out_edges) == 1 and main.mul2.b.out_edges[0].resolve() == main.mul2.m)

        self.assertTrue(len(main.mul2.m.in_edges) == 2 and main.mul2.m.in_edges[0].resolve() in (main.mul2.a, main.mul1.b) and main.mul2.m.in_edges[1].resolve() in (main.mul2.a, main.mul2.b))
        self.assertTrue(len(main.mul2.m.out_edges) == 1 and main.mul2.m.out_edges[0].resolve() == main.mul2.c)

        self.assertTrue(len(main.mul2.c.in_edges) == 1 and main.mul2.c.in_edges[0].resolve() == main.mul2.m)
        self.assertTrue(len(main.mul2.c.out_edges) == 1 and main.mul2.c.out_edges[0].resolve() == main.x4)


        # Solve
        F       = ZZ/ZZ(13)
        circuit = main.build_circuit()
        r1cs    = circuit.build_r1cs_system()

        circuit['x1'].set_value(F(7))
        circuit['x2'].set_value(F(3))
        circuit['x3'].set_value(F(2))
        res = circuit.execute()
        S   = main.els.build_solution_vector(res)

        self.assertTrue(r1cs.is_valid_assignment(S))


    def test_3fac_lexer(self):
        # Lexer -> ASG -> Algebraic Circuit -> R1CS -> QAP
        F            = ZZ/ZZ(13)
        l            = Lexer()
        prog         = l.lex(SOURCE_3FAC)
        circuit, qap = prog.build(F)

        # Check if circuit execution and QAP works
        circuit['x1'].set_value(F(7))
        circuit['x2'].set_value(F(3))
        circuit['x3'].set_value(F(2))
        res = circuit.execute()
        S   = prog.components['main'].els.build_solution_vector(res)

        self.assertTrue(qap.is_valid_assignment(S))

        # Make sure it doesn't if the solution is wrong
        S_bad    = [e for e in S]
        S_bad[0] = F(1)
        self.assertFalse(qap.is_valid_assignment(S_bad))


    def test_3fac_CRS_example(self):
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

        self.assertEqual(g1A, E6(35, 15))
        self.assertEqual(g1C, E6(13, 28))
        self.assertEqual(g2B, E6(7*y**2, 27*y**3))


    def test_3fac_groth16_example(self):
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

        self.assertEqual(proof.g1A, E6(35, 15))
        self.assertEqual(proof.g1C, E6(13, 28))
        self.assertEqual(proof.g2B, E6(7*y**2, 27*y**3))

        self.assertTrue(proof.verify(I))
        self.assertFalse(proof.verify([Fr(3)]))


    def test_3fac_complete_compilation(self):
        # Lexer -> ASG -> Algebraic Circuit -> R1CS -> QAP
        Fr           = ZZ/ZZ(13)
        l            = Lexer()
        prog         = l.lex(SOURCE_3FAC)
        circuit, qap = prog.build(Fr)

        # Check if circuit execution and QAP works
        circuit['x1'].set_value(Fr(7))
        circuit['x2'].set_value(Fr(3))
        circuit['x3'].set_value(Fr(2))
        res = circuit.execute()
        S   = prog.components['main'].els.build_solution_vector(res)

        I, W = S[:1], S[1:]

        # Build SNARK
        st = SimulationTrapdoor.generate(Fr)
        F  = ZZ/ZZ(43)
        E  = EllipticCurve(F(0), F(6))

        y     = Symbol('y')
        P     = F[y]
        F43_6 = FF(43, 6, reducing_poly=y**6 + 6)

        E6 = EllipticCurve(F43_6(E.a), F43_6(E.b))
        g1 = E6(13, 15)
        g2 = E6(7*y**2, 16*y**3)

        params = Groth16Parameters(G1=E, G2=E6, g1=g1, g2=g2, Fr=Fr)
        crs    = CRS.generate(qap, params, st, num_instances=len(I))
        proof  = Groth16Proof.generate(crs, I, W)

        self.assertTrue(proof.verify(I))
        self.assertFalse(proof.verify([Fr(3)]))


    def test_3fac_groth16_forgery_example(self):
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
        proof  = Groth16Proof.forge(crs, I, st, A=Fr(9), B=Fr(3))

        self.assertEqual(proof.g1A, E6(35, 15))
        self.assertEqual(proof.g1C, E6(33, 9))
        self.assertEqual(proof.g2B, E6(42*y**2, 16*y**3))
        self.assertTrue(proof.verify(I))
