; Easy satisfiable SMT-LIB formula
; Linear integer arithmetic - should solve quickly
(set-logic QF_LIA)
(declare-fun x () Int)
(declare-fun y () Int)
(declare-fun z () Int)

; Simple constraints with an obvious solution
(assert (> x 0))
(assert (> y 0))
(assert (> z 0))
(assert (< (+ x y z) 100))
(assert (= (+ x y) (* 2 z)))
(assert (>= x y))

(check-sat)
(exit)
