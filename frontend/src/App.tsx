import { HashRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import DashboardPage from "./pages/DashboardPage";
import PerceptionPage from "./pages/PerceptionPage";
import InspectionPage from "./pages/InspectionPage";
import SettingsPage from "./pages/SettingsPage";

// HashRouter: the app is deployed as static files to arbitrary hosts/sub-paths
// (nginx, a file share, behind a proxy) with no server-side rewrite rules, so
// hash routing keeps deep links + refresh working everywhere.
export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/perception" element={<PerceptionPage />} />
          <Route path="/inspection" element={<InspectionPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}
