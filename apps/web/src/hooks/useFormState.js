import { useState } from "react";

export function useFormState(initialValues, validate) {
  const [values, setValues] = useState(initialValues);
  const [errors, setErrors] = useState({});

  const setValue = (name, value) => {
    setValues((current) => ({ ...current, [name]: value }));
    setErrors((current) => ({ ...current, [name]: "" }));
  };

  const reset = () => {
    setValues(initialValues);
    setErrors({});
  };

  const runValidation = () => {
    const nextErrors = validate ? validate(values) : {};
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  return { values, errors, setValue, reset, runValidation };
}

