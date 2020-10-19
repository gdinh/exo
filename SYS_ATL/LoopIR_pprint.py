import re
import textwrap

from .prelude import *
from .LoopIR import UAST, front_ops, LoopIR
from . import shared_types as T

# google python formatting project
# to save myself the trouble of being overly clever
from yapf.yapflib.yapf_api import FormatCode
# run the function FormatCode to transform
# one string into a formatted string

# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
#   Notes on Layout Schemes...

"""
  functions should return a list of strings, one for each line

  standard inputs
  tab     - holds a string of white-space
  prec    - the operator precedence of the surrounding text
            if this string contains a lower precedence operation then
            we must wrap it in parentheses.
"""

# We expect pprint to install functions on the IR rather than
# expose functions; therefore hide all variables as local
__all__ = []


# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Operator Precedence

op_prec = {
    "or":     10,
    #
    "and":    20,
    #
    "<":      30,
    ">":      30,
    "<=":     30,
    ">=":     30,
    "==":     30,
    #
    "+":      40,
    "-":      40,
    #
    "*":      50,
    "/":      50,
    #
    # unary - 60
}

# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# UAST Pretty Printing


@extclass(UAST.proc)
@extclass(UAST.fnarg)
@extclass(UAST.stmt)
@extclass(UAST.expr)
def __str__(self):
    return UAST_PPrinter(self).str()
del __str__


class UAST_PPrinter:
    def __init__(self, node):
        self._node = node

        self.env = Environment()
        self._tab = ""
        self._lines = []

        if isinstance(node, UAST.proc):
            self.pproc(node)
        elif isinstance(node, UAST.fnarg):
            self.addline(self.pfnarg(node))
        elif isinstance(node, UAST.stmt):
            self.pstmts([node])
        elif isinstance(node, UAST.expr):
            self.addline(self.pexpr(node))
        else:
            assert False, f"cannot print a {type(node)}"

    def str(self):
        fmtstr, linted = FormatCode("\n".join(self._lines))
        assert linted, "generated unlinted code..."
        return fmtstr

    def push(self):
        self.env.push()
        self._tab = self._tab + "  "

    def pop(self):
        self.env.pop()
        self._tab = self._tab[:-2]

    def addline(self, line):
        self._lines.append(f"{self._tab}{line}")

    def new_name(self, nm):
        strnm   = str(nm)
        if strnm not in self.env:
            self.env[strnm] = strnm
            return strnm
        else:
            s = self.env[strnm]
            m = re.match('^(.*)_([0-9]*)$', s)
            # either post-pend a _1 or increment the post-pended counter
            if not m:
                s = s + "_1"
            else:
                s = f"{m[1]}_{int(m[2]) + 1}"
            self.env[strnm] = s
            return s

    def get_name(self, nm):
        strnm = str(nm)
        if strnm in self.env:
            return self.env[strnm]
        else:
            return repr(nm)

    def pproc(self, p):
        name = p.name or "_anon_"
        args = [f"{self.new_name(sz)} : size" for sz in p.sizes]
        args += [self.pfnarg(a) for a in p.args]
        self.addline(f"def {name}({','.join(args)}):")

        self.push()
        self.pstmts(p.body)
        self.pop()

    def pfnarg(self, a):
        return f"{self.new_name(a.name)} : {a.type} @ {a.effect}"

    def pstmts(self, body):
        for stmt in body:
            if type(stmt) is UAST.Pass:
                self.addline("pass")
            elif type(stmt) is UAST.Assign or type(stmt) is UAST.Reduce:
                op = "=" if type(stmt) is UAST.Assign else "+="

                rhs = self.pexpr(stmt.rhs)

                if len(stmt.idx) > 0:
                    idx = [self.pexpr(e) for e in stmt.idx]
                    lhs = f"{self.new_name(stmt.name)}[{','.join(idx)}]"
                else:
                    lhs = self.new_name(stmt.name)

                self.addline(f"{lhs} {op} {rhs}")
            elif type(stmt) is UAST.Alloc:
                self.addline(f"{self.new_name(stmt.name)} : {self.type}")
            elif type(stmt) is UAST.If:
                cond = self.pexpr(stmt.cond)
                self.addline(f"if {cond}:")
                self.push()
                self.pstmts(stmt.body)
                self.pop()
                if len(stmt.orelse) > 0:
                    self.addline("else:")
                    self.push()
                    self.pstmts(stmt.orelse)
                    self.pop()
            elif type(stmt) is UAST.ForAll:
                cond = self.pexpr(stmt.cond)
                self.addline(f"for {self.new_name(stmt.iter)} in {cond}:")
                self.push()
                self.pstmts(stmt.body)
                self.pop()
            else:
                assert False, "unrecognized stmt type"

    def pexpr(self, e, prec=0):
        if type(e) is UAST.Read:
            if len(e.idx) > 0:
                idx = [self.pexpr(i) for i in e.idx]
                return f"{self.get_name(e.name)}[{','.join(idx)}]"
            else:
                return self.get_name(e.name)
        elif type(e) is UAST.Const:
            return str(e.val)
        elif type(e) is UAST.BinOp:
            local_prec = op_prec[e.op]
            # increment rhs by 1 to account for left-associativity
            lhs = self.pexpr(e.lhs, prec=local_prec)
            rhs = self.pexpr(e.rhs, prec=local_prec+1)
            s = f"{lhs} {e.op} {rhs}"
            # if we have a lower precedence than the environment...
            if local_prec < prec:
                s = f"({s})"
            return s
        elif type(e) is UAST.USub:
            return f"-{self.pexpr(e.arg,prec=60)}"
        elif type(e) is UAST.ParRange:
            return f"par({self.pexpr(e.lo)},{self.pexpr(e.hi)})"
        else:
            assert False, "unrecognized expr type"





# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# LoopIR Pretty Printing


@extclass(LoopIR.proc)
@extclass(LoopIR.fnarg)
@extclass(LoopIR.stmt)
@extclass(LoopIR.expr)
@extclass(LoopIR.pred)
@extclass(LoopIR.aexpr)
def __str__(self):
    return LoopIR_PPrinter(self).str()
del __str__


class LoopIR_PPrinter:
    def __init__(self, node):
        self._node = node

        self.env = Environment()
        self._tab = ""
        self._lines = []

        if isinstance(node, UAST.proc):
            self.pproc(node)
        elif isinstance(node, UAST.fnarg):
            self.addline(self.pfnarg(node))
        elif isinstance(node, UAST.stmt):
            self.pstmts([node])
        elif isinstance(node, UAST.expr):
            self.addline(self.pexpr(node))
        else:
            assert False, f"cannot print a {type(node)}"

    def str(self):
        fmtstr, linted = FormatCode("\n".join(self._lines))
        assert linted, "generated unlinted code..."
        return fmtstr

    def push(self):
        self.env.push()
        self._tab = self._tab + "  "

    def pop(self):
        self.env.pop()
        self._tab = self._tab[:-2]

    def addline(self, line):
        self._lines.append(f"{self._tab}{line}")

    def new_name(self, nm):
        strnm   = str(nm)
        if strnm not in self.env:
            self.env[strnm] = strnm
            return strnm
        else:
            s = self.env[strnm]
            m = re.match('^(.*)_([0-9]*)$', s)
            # either post-pend a _1 or increment the post-pended counter
            if not m:
                s = s + "_1"
            else:
                s = f"{m[1]}_{int(m[2]) + 1}"
            self.env[strnm] = s
            return s

    def get_name(self, nm):
        strnm = str(nm)
        if strnm in self.env:
            return self.env[strnm]
        else:
            return repr(nm)

    def pproc(self, p):
        name = p.name or "_anon_"
        args = [f"{self.new_name(sz)} : size" for sz in p.sizes]
        args += [self.pfnarg(a) for a in p.args]
        self.addline(f"def {name}({','.join(args)}):")

        self.push()
        self.pstmts(p.body)
        self.pop()

    def pfnarg(self, a):
        return f"{self.new_name(a.name)} : {a.type} @ {a.effect}"

    def pstmts(self, body):
        for stmt in body:
            if type(stmt) is UAST.Pass:
                self.addline("pass")
            elif type(stmt) is UAST.Assign or type(stmt) is UAST.Reduce:
                op = "=" if type(stmt) is UAST.Assign else "+="

                rhs = self.pexpr(stmt.rhs)

                if len(stmt.idx) > 0:
                    idx = [self.pexpr(e) for e in stmt.idx]
                    lhs = f"{self.new_name(stmt.name)}[{','.join(idx)}]"
                else:
                    lhs = self.new_name(stmt.name)

                self.addline(f"{lhs} {op} {rhs}")
            elif type(stmt) is UAST.Alloc:
                self.addline(f"{self.new_name(stmt.name)} : {self.type}")
            elif type(stmt) is UAST.If:
                cond = self.pexpr(stmt.cond)
                self.addline(f"if {cond}:")
                self.push()
                self.pstmts(stmt.body)
                self.pop()
                if len(stmt.orelse) > 0:
                    self.addline("else:")
                    self.push()
                    self.pstmts(stmt.orelse)
                    self.pop()
            elif type(stmt) is UAST.ForAll:
                cond = self.pexpr(stmt.cond)
                self.addline(f"for {self.new_name(stmt.iter)} in {cond}:")
                self.push()
                self.pstmts(stmt.body)
                self.pop()
            else:
                assert False, "unrecognized stmt type"

    def pexpr(self, e, prec=0):
        if type(e) is UAST.Read:
            if len(e.idx) > 0:
                idx = [self.pexpr(i) for i in e.idx]
                return f"{self.get_name(e.name)}[{','.join(idx)}]"
            else:
                return self.get_name(e.name)
        elif type(e) is UAST.Const:
            return str(e.val)
        elif type(e) is UAST.BinOp:
            local_prec = op_prec[e.op]
            # increment rhs by 1 to account for left-associativity
            lhs = self.pexpr(e.lhs, prec=local_prec)
            rhs = self.pexpr(e.rhs, prec=local_prec+1)
            s = f"{lhs} {e.op} {rhs}"
            # if we have a lower precedence than the environment...
            if local_prec < prec:
                s = f"({s})"
            return s
        elif type(e) is UAST.USub:
            return f"-{self.pexpr(e.arg,prec=60)}"
        elif type(e) is UAST.ParRange:
            return f"par({self.pexpr(e.lo)},{self.pexpr(e.hi)})"
        else:
            assert False, "unrecognized expr type"
