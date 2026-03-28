import { Routes, Route } from "react-router";
import { AppLayout } from "@/components/layout/AppLayout";
import { DashboardPage } from "@/pages/dashboard/DashboardPage";
import { ProjectListPage } from "@/pages/projects/ProjectListPage";
import { ProjectNewPage } from "@/pages/projects/ProjectNewPage";
import { ProjectLayout } from "@/pages/projects/ProjectLayout";
import { OverviewTab } from "@/pages/projects/OverviewTab";
import { ImportTab } from "@/pages/projects/ImportTab";
import { GraphTab } from "@/pages/projects/GraphTab";
import { FinetuneTab } from "@/pages/projects/FinetuneTab";
import { PipelineTab } from "@/pages/projects/PipelineTab";
import { ProjectSettingsTab } from "@/pages/projects/ProjectSettingsTab";
import { ChatPage } from "@/pages/chat/ChatPage";
import { SchedulerPage } from "@/pages/scheduler/SchedulerPage";
import { ModelsPage } from "@/pages/models/ModelsPage";
import { SettingsPage } from "@/pages/settings/SettingsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="projects" element={<ProjectListPage />} />
        <Route path="projects/new" element={<ProjectNewPage />} />
        <Route path="projects/:name" element={<ProjectLayout />}>
          <Route index element={<OverviewTab />} />
          <Route path="overview" element={<OverviewTab />} />
          <Route path="import" element={<ImportTab />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="pipeline" element={<PipelineTab />} />
          <Route path="graph" element={<GraphTab />} />
          <Route path="finetune" element={<FinetuneTab />} />
          <Route path="settings" element={<ProjectSettingsTab />} />
        </Route>
        <Route path="chat" element={<ChatPage />} />
        <Route path="chat/:conversationId" element={<ChatPage />} />
        <Route path="scheduler" element={<SchedulerPage />} />
        <Route path="models" element={<ModelsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
