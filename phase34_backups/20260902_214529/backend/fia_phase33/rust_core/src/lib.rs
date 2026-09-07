use pyo3::prelude::*;
#[pyfunction]
fn weighted_mean(values: Vec<f64>, weights: Vec<f64>) -> PyResult<f64> {
    if values.len()!=weights.len() || values.is_empty(){ return Ok(0.0); }
    let den:f64=weights.iter().map(|x|x.max(0.0)).sum();
    if den<=1e-12 {return Ok(0.0)}
    Ok(values.iter().zip(weights.iter()).map(|(v,w)|v*w.max(0.0)).sum::<f64>()/den)
}
#[pymodule]
fn fia_phase33_rust(m: &Bound<'_, PyModule>) -> PyResult<()> { m.add_function(wrap_pyfunction!(weighted_mean,m)?)?; Ok(()) }
