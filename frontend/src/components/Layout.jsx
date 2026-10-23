import { NavLink, Link } from "react-router-dom";
import { useAsync } from "../hooks/useAsync.js";
import { API_BASE_URL, api } from "../services/api.js";
import Alert from "./Alert.jsx";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/requests/new", label: "New request" },
  { to: "/blood-banks", label: "Blood banks" },
  { to: "/donors", label: "Donors" },
];

function Drop() {
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <path fill="#fff" d="M16 2C16 2 6 14 6 20a10 10 0 0 0 20 0C26 14 16 2 16 2z" />
    </svg>
  );
}

export default function Layout({ children }) {
  const health = useAsync(() => api.health(), []);
  return (
    <>
      <a className="skip" href="#main">Skip to main content</a>
      <header className="site-header">
        <div className="wrap header-row">
          <Link to="/" className="brand" aria-label="RaktSetu home">
            <Drop />
            <span>RaktSetu</span>
          </Link>
          <nav aria-label="Main">
            <ul className="nav">
              {NAV.map((n) => (
                <li key={n.to}>
                  <NavLink to={n.to} end={n.end} className={({ isActive }) => (isActive ? "active" : undefined)}>
                    {n.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <p className="server-state" role="status">
            {health.loading && !health.data ? "Checking server..." : health.data ? "✔ Server connected" : "✖ Server not reachable"}
          </p>
        </div>
        <div className="demo-banner">
          <div className="wrap">
            <strong>Demonstration only.</strong> Every patient, donor, blood bank and event here is fictional or simulated.
            This is not for real medical decisions.
          </div>
        </div>
      </header>
      <main id="main" className="wrap main" tabIndex={-1}>
        {health.error && (
          <Alert tone="error" title="The RaktSetu server is not reachable">
            Start the backend, then{" "}
            <button type="button" className="link-btn" onClick={health.reload}>check again</button>. Expected address: {API_BASE_URL}
          </Alert>
        )}
        {children}
      </main>
      <footer className="site-footer">
        <div className="wrap">
          RaktSetu is a hackathon prototype. Final blood group compatibility, donor eligibility, screening and stock
          confirmation must be done by qualified professionals. The history shown here is an application log, not a
          certified record.
        </div>
      </footer>
    </>
  );
}
