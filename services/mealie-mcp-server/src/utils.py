def format_api_params(params: dict) -> dict:
    """Formats list and None values in a dictionary for API parameters."""
    output = {}
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, list):
            output[k] = ",".join(v)
        else:
            output[k] = v
    return output
