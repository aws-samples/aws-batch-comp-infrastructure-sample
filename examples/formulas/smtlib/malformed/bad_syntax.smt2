; Malformed SMT-LIB - invalid syntax
(set-logic QF_LIA)
(declare-fun x ( Int)  ; Missing closing paren
(assert (> x 0))
(check-sat
(exit)
