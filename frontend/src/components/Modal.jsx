import { useEffect, useRef } from 'react'

const FOCUSABLE = 'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])'

// Accessible dialog: Escape and a backdrop click close it, Tab stays inside it,
// focus returns to the button that opened it, and the page behind does not scroll.
export default function Modal({ title, subtitle, onClose, children }) {
  const panel = useRef(null)
  // Keep the latest callback in a ref so the effect below runs once per open.
  // Otherwise a parent passing a fresh function each render would re-run it,
  // and the "element to return focus to" would become the close button.
  const closeRef = useRef(onClose)
  closeRef.current = onClose

  useEffect(() => {
    const opener = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    panel.current?.querySelector('[data-autofocus]')?.focus()

    function onKey(event) {
      if (event.key === 'Escape') { closeRef.current(); return }
      if (event.key !== 'Tab' || !panel.current) return
      const items = [...panel.current.querySelectorAll(FOCUSABLE)]
      if (items.length === 0) return
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }

    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previousOverflow
      opener?.focus?.()
    }
  }, [])

  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) closeRef.current() }}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} ref={panel}>
        <div className="modal-head">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close" data-autofocus>✕</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  )
}
