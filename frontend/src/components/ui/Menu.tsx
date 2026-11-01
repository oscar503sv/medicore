import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import { MoreHorizontal, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/cn'

export interface MenuItem {
  label: string
  icon?: LucideIcon
  onSelect: () => void
  tone?: 'default' | 'danger'
}

/** "⋯" button with a small action menu (portal, right-aligned, keyboard navigable). */
export function Menu({ items, label }: { items: MenuItem[]; label: string }) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [pos, setPos] = useState<React.CSSProperties>({})
  const buttonRef = useRef<HTMLButtonElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  const show = () => {
    const r = buttonRef.current?.getBoundingClientRect()
    if (!r) return
    const up = window.innerHeight - r.bottom < 48 * items.length + 16
    setPos({
      right: window.innerWidth - r.right,
      ...(up ? { bottom: window.innerHeight - r.top + 4 } : { top: r.bottom + 4 }),
    })
    setActive(0)
    setOpen(true)
  }
  const hide = (refocus = true) => {
    setOpen(false)
    if (refocus) buttonRef.current?.focus()
  }
  const run = (i: number) => {
    hide()
    items[i]?.onSelect()
  }

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node
      if (!buttonRef.current?.contains(t) && !listRef.current?.contains(t)) hide(false)
    }
    const onScroll = () => hide(false)
    document.addEventListener('mousedown', onDown)
    window.addEventListener('scroll', onScroll, true)
    return () => {
      document.removeEventListener('mousedown', onDown)
      window.removeEventListener('scroll', onScroll, true)
    }
  }, [open])

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        show()
      }
      return
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const d = e.key === 'ArrowDown' ? 1 : -1
      setActive((a) => (a + d + items.length) % items.length)
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      run(active)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      hide()
    } else if (e.key === 'Tab') {
      hide(false)
    }
  }

  if (items.length === 0) return null

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-label={label}
        title={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        aria-activedescendant={open ? `${id}-${active}` : undefined}
        onClick={() => (open ? hide() : show())}
        onKeyDown={onKeyDown}
        className={cn(
          'rounded-md p-1.5 text-tx-3 transition-colors hover:bg-surface-2 hover:text-tx',
          'focus:outline-none focus-visible:ring-1 focus-visible:ring-accent',
          open && 'bg-surface-2 text-tx',
        )}
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>
      {open &&
        createPortal(
          <ul
            ref={listRef}
            id={id}
            role="menu"
            className="fixed z-[100] min-w-44 rounded-lg border border-line bg-surface p-1 shadow-lg animate-pop-in"
            style={pos}
          >
            {items.map((it, i) => {
              const Icon = it.icon
              return (
                <li
                  key={it.label}
                  id={`${id}-${i}`}
                  role="menuitem"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => run(i)}
                  onMouseEnter={() => setActive(i)}
                  className={cn(
                    'flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm',
                    i === active && 'bg-surface-2',
                    it.tone === 'danger' ? 'text-danger' : 'text-tx',
                  )}
                >
                  {Icon && <Icon className="h-4 w-4 shrink-0 opacity-80" />}
                  {it.label}
                </li>
              )
            })}
          </ul>,
          document.body,
        )}
    </>
  )
}
