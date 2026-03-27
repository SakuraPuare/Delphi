import { AnimatePresence, motion } from "framer-motion";
import { useStore } from "@/store";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
import ChatPanel from "@/components/ChatPanel";
import InputBar from "@/components/InputBar";

export default function App() {
  const sidebarOpen = useStore((s) => s.sidebarOpen);
  const toggleSidebar = useStore((s) => s.toggleSidebar);

  return (
    <div className="flex h-dvh overflow-hidden bg-dark-bg">
      {/* Desktop sidebar -- Sidebar manages its own width animation */}
      <div className="hidden md:block">
        <Sidebar />
      </div>

      {/* Mobile sidebar overlay */}
      <AnimatePresence>
        {sidebarOpen && (
          <>
            <motion.div
              key="overlay"
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.5 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black md:hidden"
              onClick={toggleSidebar}
            />
            <motion.div
              key="mobile-sidebar"
              initial={{ x: -280 }}
              animate={{ x: 0 }}
              exit={{ x: -280 }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
              className="fixed inset-y-0 left-0 z-50 w-[280px] md:hidden"
            >
              <Sidebar />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Main area */}
      <div className="flex min-w-0 flex-1 flex-col">
        <Header />
        <ChatPanel />
        <InputBar />
      </div>
    </div>
  );
}
