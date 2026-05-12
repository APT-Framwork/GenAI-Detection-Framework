// observable-store.ts — global "show this observable" drawer state.
//
// Any IOC string (IP / hash / domain / email) anywhere in the app can call
// openObservable("1.2.3.4") to slide the enrichment drawer in. We persist
// open state on globalThis so HMR re-evaluation doesn't tear the drawer
// down mid-session.

import { useEffect, useState } from "react";

interface State {
  open: boolean;
  value: string | null;
}

interface ObservableGlobal {
  __strixObservableState?: State;
  __strixObservableListeners?: Set<() => void>;
}

const _g = globalThis as unknown as ObservableGlobal;
const _state: State = (_g.__strixObservableState ??= { open: false, value: null });
const _listeners: Set<() => void> = (_g.__strixObservableListeners ??= new Set());

function _emit(): void {
  _listeners.forEach((fn) => fn());
}

export function openObservable(value: string): void {
  const v = value.trim();
  if (!v) return;
  _state.open = true;
  _state.value = v;
  _emit();
}

export function closeObservable(): void {
  if (!_state.open && _state.value === null) return;
  _state.open = false;
  _state.value = null;
  _emit();
}

export function useObservableDrawer(): State {
  const [, setTick] = useState(0);
  useEffect(() => {
    const fn = () => setTick((n) => n + 1);
    _listeners.add(fn);
    return () => {
      _listeners.delete(fn);
    };
  }, []);
  return { open: _state.open, value: _state.value };
}
