import { useState, useRef, useEffect, useId } from 'react'

export function InfoTip({ text }) {
  const [show, setShow] = useState(false)
  const [pos, setPos] = useState('top')
  const tipRef = useRef(null)
  const id = useId()

  useEffect(() => {
    if (show && tipRef.current) {
      const rect = tipRef.current.getBoundingClientRect()
      if (rect.top < 8) setPos('bottom')
      else if (rect.bottom > window.innerHeight - 8) setPos('top')
    }
  }, [show])

  return (
    <span
      className="info-tip-wrap"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => { setShow(false); setPos('top') }}
      onFocus={() => setShow(true)}
      onBlur={() => { setShow(false); setPos('top') }}
    >
      <svg
        className="info-tip-icon"
        viewBox="0 0 16 16"
        fill="currentColor"
        role="img"
        aria-describedby={show ? id : undefined}
        aria-label="More information"
        tabIndex={0}
      >
        <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0-1.3A5.7 5.7 0 1 0 8 2.3a5.7 5.7 0 0 0 0 11.4zM7.25 7h1.5v4.5h-1.5V7zm0-2.5h1.5V6h-1.5V4.5z" />
      </svg>
      {show && (
        <span ref={tipRef} id={id} role="tooltip" className={`info-tip-bubble info-tip-${pos}`}>
          {text}
        </span>
      )}
    </span>
  )
}

export function WithTooltip({ text, children }) {
  const [show, setShow] = useState(false)
  const tipRef = useRef(null)
  const id = useId()

  return (
    <span
      className="with-tooltip-wrap"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      aria-describedby={show ? id : undefined}
    >
      {children}
      {show && (
        <span ref={tipRef} id={id} role="tooltip" className="info-tip-bubble info-tip-top">
          {text}
        </span>
      )}
    </span>
  )
}
