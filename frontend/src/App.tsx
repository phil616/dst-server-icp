import { Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { AuthGate } from "./components/AuthGate";
import { About } from "./modules/about/About";
import { ContactsPanel } from "./modules/contacts/ContactsPanel";
import { Dashboard } from "./modules/dashboard/Dashboard";
import { InstallCenter } from "./modules/install/InstallCenter";
import { InstanceDetail } from "./modules/instances/InstanceDetail";
import { InstanceList } from "./modules/instances/InstanceList";
import { ProxySettings } from "./modules/proxy/ProxySettings";
import { TaskQueueProvider } from "./task-queue-context";

export default function App() {
  return (
    <AuthGate>
      <TaskQueueProvider>
        <AppLayout>
          <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/instances" element={<InstanceList />} />
          <Route path="/instances/:id" element={<InstanceDetail />} />
          <Route path="/install" element={<InstallCenter />} />
          <Route path="/contacts" element={<ContactsPanel />} />
          <Route path="/proxy" element={<ProxySettings />} />
          <Route path="/about" element={<About />} />
          </Routes>
        </AppLayout>
      </TaskQueueProvider>
    </AuthGate>
  );
}
