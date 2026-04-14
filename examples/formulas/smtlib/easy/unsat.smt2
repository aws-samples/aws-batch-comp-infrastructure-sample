; Easy unsatisfiable SMT-LIB formula
; Linear integer arithmetic with contradictory constraints
(set-logic QF_LIA)
(declare-fun x () Int)
(declare-fun y () Int)

; x > y and y > x cannot both be true
(assert (> x y))
(assert (> y x))

(check-sat)
(exit)
