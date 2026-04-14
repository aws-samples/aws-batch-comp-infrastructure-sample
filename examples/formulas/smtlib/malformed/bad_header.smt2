; Malformed SMT-LIB - missing set-logic
(declare-fun x () Int)
(assert (> x 0))
(check-sat)
(exit)
