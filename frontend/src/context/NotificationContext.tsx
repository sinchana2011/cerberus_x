import * as React from "react";

export type NotificationKind = "info" | "success" | "warning" | "error";

export interface NotificationItem {
  id: string;
  kind: NotificationKind;
  title: string;
  message?: string;
}

interface NotificationContextValue {
  notifications: NotificationItem[];
  notify: (kind: NotificationKind, title: string, message?: string) => void;
  dismiss: (id: string) => void;
}

const NotificationContext = React.createContext<NotificationContextValue | undefined>(
  undefined
);

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [notifications, setNotifications] = React.useState<NotificationItem[]>([]);

  const dismiss = React.useCallback((id: string) => {
    setNotifications((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const notify = React.useCallback(
    (kind: NotificationKind, title: string, message?: string) => {
      const id = `ntf_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      setNotifications((prev) => [...prev.slice(-3), { id, kind, title, message }]);
      window.setTimeout(() => {
        setNotifications((prev) => prev.filter((item) => item.id !== id));
      }, 6000);
    },
    []
  );

  return (
    <NotificationContext.Provider value={{ notifications, notify, dismiss }}>
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications() {
  const ctx = React.useContext(NotificationContext);
  if (!ctx) {
    throw new Error("useNotifications must be used inside NotificationProvider");
  }
  return ctx;
}
