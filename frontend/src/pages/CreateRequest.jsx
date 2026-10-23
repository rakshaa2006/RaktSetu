import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Alert from "../components/Alert.jsx";
import Field, { describedBy } from "../components/Field.jsx";
import Spinner from "../components/Spinner.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { usePageTitle } from "../hooks/usePageTitle.js";
import { api } from "../services/api.js";

const INITIAL = {
  patient_name: "", patient_age: "", patient_gender: "", patient_blood_group: "", component: "",
  units_required: "", hospital_name: "", location_id: "", other_location: "", urgency: "",
};

function validate(v, locations) {
  const e = {};
  const name = v.patient_name.trim();
  if (name.length < 2) e.patient_name = "Enter the patient's full name (at least 2 letters).";
  else if (!/^[\p{L} .'-]+$/u.test(name)) e.patient_name = "Use letters, spaces, full stops, apostrophes or hyphens only.";
  if (!/^\d+$/.test(v.patient_age.trim())) e.patient_age = "Enter the age in whole years, for example 42.";
  else if (Number(v.patient_age) > 120) e.patient_age = "Age must be between 0 and 120.";
  if (!v.patient_gender) e.patient_gender = "Choose a gender option.";
  if (!v.patient_blood_group) e.patient_blood_group = "Choose the patient's blood group.";
  if (!v.component) e.component = "Choose the blood component needed.";
  if (!/^\d+$/.test(v.units_required.trim()) || Number(v.units_required) < 1) e.units_required = "Enter a whole number of units, 1 or more.";
  else if (Number(v.units_required) > 20) e.units_required = "Units must be 20 or fewer.";
  if (v.hospital_name.trim().length < 2) e.hospital_name = "Enter the hospital name.";
  if (!v.location_id) e.location_id = "Choose the hospital location.";
  if (v.location_id === "OTHER" && v.other_location.trim().length < 2) e.other_location = "Type the location name.";
  if (!v.urgency) e.urgency = "Choose how urgent this request is.";
  return e;
}

export default function CreateRequest() {
  usePageTitle("Create blood request");
  const navigate = useNavigate();
  const meta = useAsync(() => api.meta(), []);
  const locations = useAsync(() => api.locations(), []);
  const [values, setValues] = useState(INITIAL);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState(null);

  if ((meta.loading && !meta.data) || (locations.loading && !locations.data)) return <Spinner label="Loading form..." />;
  if (meta.error || locations.error) {
    return (
      <Alert tone="error" title="The form could not be loaded">
        {(meta.error || locations.error).message}{" "}
        <button type="button" className="link-btn" onClick={() => { meta.reload(); locations.reload(); }}>Try again</button>
      </Alert>
    );
  }
  const m = meta.data;
  const set = (field) => (e) => {
    setValues((v) => ({ ...v, [field]: e.target.value }));
    if (errors[field]) setErrors((x) => ({ ...x, [field]: undefined }));
  };
  const props = (id) => ({ id, value: values[id], onChange: set(id), "aria-invalid": errors[id] ? "true" : undefined, "aria-describedby": describedBy(id, null, errors[id]) });

  async function onSubmit(event) {
    event.preventDefault();
    if (submitting) return;
    const found = validate(values, locations.data);
    setErrors(found);
    setServerError(null);
    if (Object.keys(found).length) {
      const first = Object.keys(found)[0];
      document.getElementById(first)?.focus();
      return;
    }
    const loc = locations.data.find((l) => l.location_id === values.location_id);
    const body = {
      patient_name: values.patient_name.trim(),
      patient_age: Number(values.patient_age),
      patient_gender: values.patient_gender,
      patient_blood_group: values.patient_blood_group,
      component: values.component,
      units_required: Number(values.units_required),
      hospital_name: values.hospital_name.trim(),
      hospital_location: loc ? loc.name : values.other_location.trim(),
      hospital_latitude: loc ? loc.latitude : null,
      hospital_longitude: loc ? loc.longitude : null,
      urgency: values.urgency,
    };
    setSubmitting(true);
    try {
      const created = await api.createRequest(body);
      navigate(`/requests/${created.id}`, { state: { justCreated: true } });
    } catch (err) {
      if (err.fieldErrors && Object.keys(err.fieldErrors).length) {
        const map = { hospital_location: "location_id", hospital_latitude: "location_id", hospital_longitude: "location_id" };
        const mapped = {};
        for (const [k, msg] of Object.entries(err.fieldErrors)) mapped[map[k] || k] = msg;
        setErrors(mapped);
      }
      setServerError(err.message);
      setSubmitting(false);
    }
  }

  const options = (list) => list.map((o) => <option key={o} value={o}>{o}</option>);
  return (
    <>
      <h1>Create blood request</h1>
      <p className="muted">Use fictional patient details only. The request is saved and ranked options are shown straight away.</p>
      {serverError && <Alert tone="error" title="The request was not saved">{serverError}</Alert>}
      {Object.keys(errors).filter((k) => errors[k]).length > 0 && (
        <Alert tone="warning" title="Please fix the highlighted fields">Each field with a problem explains what to change.</Alert>
      )}
      <form onSubmit={onSubmit} noValidate>
        <fieldset className="panel">
          <legend>Patient details (fictional)</legend>
          <Field id="patient_name" label="Patient full name" required error={errors.patient_name}>
            <input type="text" autoComplete="off" maxLength={100} {...props("patient_name")} />
          </Field>
          <div className="grid-3">
            <Field id="patient_age" label="Patient age in years" required error={errors.patient_age}>
              <input type="text" inputMode="numeric" autoComplete="off" maxLength={3} {...props("patient_age")} />
            </Field>
            <Field id="patient_gender" label="Patient gender" required error={errors.patient_gender}>
              <select {...props("patient_gender")}>
                <option value="">Choose...</option>
                {options(m.genders)}
              </select>
            </Field>
            <Field id="patient_blood_group" label="Patient blood group" required error={errors.patient_blood_group}>
              <select {...props("patient_blood_group")}>
                <option value="">Choose...</option>
                {options(m.blood_groups)}
              </select>
            </Field>
          </div>
        </fieldset>

        <fieldset className="panel">
          <legend>Blood request details</legend>
          <div className="grid-3">
            <Field id="component" label="Blood component needed" required error={errors.component}>
              <select {...props("component")}>
                <option value="">Choose...</option>
                {options(m.components)}
              </select>
            </Field>
            <Field id="units_required" label="Number of units" required error={errors.units_required}>
              <input type="text" inputMode="numeric" autoComplete="off" maxLength={2} {...props("units_required")} />
            </Field>
            <Field id="urgency" label="Urgency" required error={errors.urgency}>
              <select {...props("urgency")}>
                <option value="">Choose...</option>
                {options(m.urgencies)}
              </select>
            </Field>
          </div>
          <Field id="hospital_name" label="Hospital name" required error={errors.hospital_name}>
            <input type="text" autoComplete="off" maxLength={120} {...props("hospital_name")} />
          </Field>
          <Field id="location_id" label="Hospital location" required error={errors.location_id}
            hint="Choosing a listed area lets RaktSetu show straight-line distances. Choose 'Other' if it is not listed.">
            <select {...props("location_id")} aria-describedby={describedBy("location_id", true, errors.location_id)}>
              <option value="">Choose...</option>
              {locations.data.map((l) => <option key={l.location_id} value={l.location_id}>{l.name}</option>)}
              <option value="OTHER">Other (not listed - distances will be unknown)</option>
            </select>
          </Field>
          {values.location_id === "OTHER" && (
            <Field id="other_location" label="Location name" required error={errors.other_location}>
              <input type="text" autoComplete="off" maxLength={120} {...props("other_location")} />
            </Field>
          )}
          <p className="small muted">The request ID, creation time and starting status (Open) are added automatically.</p>
        </fieldset>

        <div className="btn-row">
          <button type="submit" className="btn btn-primary btn-large" disabled={submitting}>
            {submitting ? "Saving request..." : "Save request and find options"}
          </button>
        </div>
      </form>
    </>
  );
}
