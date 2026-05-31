import { Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { Dashboard } from "./modules/dashboard/Dashboard";
import { InstallCenter } from "./modules/install/InstallCenter";
import { InstanceDetail } from "./modules/instances/InstanceDetail";
import { InstanceList } from "./modules/instances/InstanceList";
import { ProxySettings } from "./modules/proxy/ProxySettings";

export default function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/instances" element={<InstanceList />} />
        <Route path="/instances/:id" element={<InstanceDetail />} />
        <Route path="/install" element={<InstallCenter />} />
        <Route path="/proxy" element={<ProxySettings />} />
      </Routes>
    </AppLayout>
  );
}
