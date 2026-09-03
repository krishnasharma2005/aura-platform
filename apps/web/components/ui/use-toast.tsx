"use client";

import * as React from "react";
import type { ToastActionElement, ToastProps } from "@/components/ui/toast";

const TOAST_LIMIT = 3;

type ToasterToast = ToastProps & {
  id: string;
  title?: React.ReactNode;
  description?: React.ReactNode;
  action?: ToastActionElement;
};

let count = 0;
function genId() {
  count = (count + 1) % Number.MAX_SAFE_INTEGER;
  return count.toString();
}

type State = { toasts: ToasterToast[] };

const listeners: Array<(state: State) => void> = [];
let memoryState: State = { toasts: [] };

function dispatch(action: { type: "ADD"; toast: ToasterToast } | { type: "DISMISS"; id?: string } | { type: "REMOVE"; id?: string }) {
  if (action.type === "ADD") {
    memoryState = { toasts: [action.toast, ...memoryState.toasts].slice(0, TOAST_LIMIT) };
  } else if (action.type === "DISMISS" || action.type === "REMOVE") {
    memoryState = {
      toasts: action.id ? memoryState.toasts.filter((t) => t.id !== action.id) : [],
    };
  }
  listeners.forEach((listener) => listener(memoryState));
}

type Toast = Omit<ToasterToast, "id">;

function toast(props: Toast) {
  const id = genId();
  dispatch({ type: "ADD", toast: { ...props, id } });
  const timeout = setTimeout(() => dispatch({ type: "REMOVE", id }), 4000);
  return {
    id,
    dismiss: () => {
      clearTimeout(timeout);
      dispatch({ type: "REMOVE", id });
    },
  };
}

function useToast() {
  const [state, setState] = React.useState<State>(memoryState);

  React.useEffect(() => {
    listeners.push(setState);
    return () => {
      const index = listeners.indexOf(setState);
      if (index > -1) listeners.splice(index, 1);
    };
  }, []);

  return { ...state, toast, dismiss: (id?: string) => dispatch({ type: "REMOVE", id }) };
}

export { useToast, toast };
