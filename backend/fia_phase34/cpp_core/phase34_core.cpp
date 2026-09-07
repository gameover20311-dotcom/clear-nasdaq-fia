// Phase34 optional C++ acceleration source. Research calculations only; no broker I/O.
#include <vector>
#include <cmath>
extern "C" double weighted_signal(const double* s,const double* w,int n){double a=0,b=0;for(int i=0;i<n;i++){a+=s[i]*w[i];b+=w[i];}return b? a/b:0.0;}
