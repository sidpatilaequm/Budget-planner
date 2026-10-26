import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

const UiContext = createContext(null)
export const useUi = () => useContext(UiContext)

export function Modal({ open, onClose, children, wide }) {
  const ref = useRef(null)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])
  return (
    <dialog ref={ref} style={wide ? { width: 'min(640px, calc(100vw - 32px))' } : undefined}
      onCancel={(e) => { e.preventDefault(); onClose?.() }}>
      {open && children}
    </dialog>
  )
}

export function UiProvider({ children }) {
  const [toastMsg, setToastMsg] = useState('')
  const [shown, setShown] = useState(false)
  const timer = useRef(null)
  const [confirmState, setConfirmState] = useState(null)

  const toast = useCallback((msg) => {
    setToastMsg(msg)
    setShown(true)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setShown(false), 3200)
  }, [])

  const confirm = useCallback((title, text, ok) => new Promise((resolve) => {
    setConfirmState({ title, text, ok, resolve })
  }), [])

  const close = (val) => { confirmState?.resolve(val); setConfirmState(null) }

  return (
    <UiContext.Provider value={{ toast, confirm }}>
      {children}
      <Modal open={!!confirmState} onClose={() => close(false)}>
        {confirmState && (
          <form className="dlg" onSubmit={(e) => { e.preventDefault(); close(true) }}>
            <h2>{confirmState.title}</h2>
            <p className="sub" style={{ margin: 0 }}>{confirmState.text}</p>
            <div className="dlgbtns">
              <button type="button" className="btn ghost" onClick={() => close(false)}>Cancel</button>
              <button type="submit" className="btn primary" autoFocus>{confirmState.ok}</button>
            </div>
          </form>
        )}
      </Modal>
      <div className={`toast ${shown ? 'show' : ''}`} role="status">{toastMsg}</div>
    </UiContext.Provider>
  )
}

export const Chevron = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
    <path d="M4 2l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

export function useLoad(fn, deps) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const reload = useCallback(async () => {
    try { setData(await fn()); setError(null) } catch (e) { setError(e.message) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { reload() }, [reload])
  return [data, reload, setData, error]
}
