from samson.core.base_object import BaseObject
from asg import Template, Component, Input, Output, ADD, MUL
from algebraic_circuit import EdgeLabelSystem
from qap import QAPSystem
from enum import Enum, auto
import re
import random

class Program(BaseObject):
    def __init__(self, context):
        self.templates  = {k:v for k,v in context.items() if type(v) is Template}
        self.components = {k:v for k,v in context.items() if type(v) is Component}
    
    def build(self, F: 'Field'):
        circuit = self.components['main'].build_circuit()
        r1cs    = circuit.build_r1cs_system()
        return circuit, QAPSystem.from_r1cs_system(F, r1cs)


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
