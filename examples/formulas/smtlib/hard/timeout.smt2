; Hard SMT-LIB formula - should timeout
; Non-linear integer arithmetic is undecidable in general
(set-logic QF_NIA)
(declare-fun a () Int)
(declare-fun b () Int)
(declare-fun c () Int)
(declare-fun d () Int)
(declare-fun e () Int)

; Constraints that create a hard search space
(assert (> a 1))
(assert (> b 1))
(assert (> c 1))
(assert (> d 1))
(assert (> e 1))
(assert (< a 1000000))
(assert (< b 1000000))
(assert (< c 1000000))
(assert (< d 1000000))
(assert (< e 1000000))

; Non-linear constraints - exponentially hard
(assert (= (* a a) (+ (* b b) (* c c))))
(assert (= (* b b) (+ (* d d) (* e e))))
(assert (= (* a b c) (* d d e e)))
(assert (> (* a b) (* c d e)))
(assert (= (mod (* a b c d e) 17) 0))
(assert (= (mod (* a a b b) 13) 1))

(check-sat)
(exit)
