import { Link, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import BankInbox from "./pages/BankInbox.jsx";
import BloodBanks from "./pages/BloodBanks.jsx";
import CreateRequest from "./pages/CreateRequest.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Donors from "./pages/Donors.jsx";
import RequestDetail from "./pages/RequestDetail.jsx";
import TimelinePage from "./pages/TimelinePage.jsx";

function NotFound() {
  return (
    <section className="panel">
      <h1>Page not found</h1>
      <p>That page does not exist.</p>
      <Link className="btn btn-primary" to="/">Go to the dashboard</Link>
    </section>
  );
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/requests/new" element={<CreateRequest />} />
        <Route path="/bank-inbox" element={<BankInbox />} />
        <Route path="/requests/:id" element={<RequestDetail />} />
        <Route path="/requests/:id/timeline" element={<TimelinePage />} />
        <Route path="/blood-banks" element={<BloodBanks />} />
        <Route path="/donors" element={<Donors />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  );
}
