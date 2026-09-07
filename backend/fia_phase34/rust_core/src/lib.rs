#[no_mangle]
pub extern "C" fn fia_weighted_signal(scores:*const f64,weights:*const f64,n:usize)->f64{if scores.is_null()||weights.is_null()||n==0{return 0.0;}let s=unsafe{std::slice::from_raw_parts(scores,n)};let w=unsafe{std::slice::from_raw_parts(weights,n)};let mut a=0.0;let mut b=0.0;for i in 0..n{a+=s[i]*w[i];b+=w[i];}if b==0.0{0.0}else{a/b}}
