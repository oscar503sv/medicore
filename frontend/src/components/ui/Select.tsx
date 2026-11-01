import {
  Children,
  forwardRef,
  isValidElement,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import { Check, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/cn'

/**
 * Drop-in replacement for a native <select>: same API (`value`, `onChange(e)` reading
 * `e.target.value`, `<option>` children), but the list is drawn by the app.
 *
 * Why: the native popup is painted by the browser/OS — Firefox on Linux takes its colours
 * from the GTK theme and ignores the page's, which left the list unreadable (light text on
 * a light popup). A custom listbox looks the same everywhere and follows the app's theme.
 */

interface Opt {
  value: string
  label: ReactNode
  text: string
  disabled: boolean
}

export interface SelectProps {
  label?: string
  value?: string | number
  onChange?: (e: { target: { value: string } }) => void
  children?: ReactNode
  className?: string
  disabled?: boolean
  id?: string
  'aria-label'?: string
  /** `bare`: no border/background, for inline use (e.g. a time inside a row). */
  variant?: 'default' | 'bare'
}

const MAX_HEIGHT = 280

export const Select = forwardRef<HTMLButtonElement, SelectProps>(
  (
    { label, value, onChange, children, className, disabled, id, variant = 'default', ...aria },
    ref,
  ) => {
    const options = collectOptions(children)
    const current = String(value ?? '')
    const selectedIndex = options.findIndex((o) => o.value === current)
    const selected = options[selectedIndex]

    const autoId = useId()
    const buttonId = id ?? `${autoId}-button`
    const listId = `${autoId}-list`
    const labelId = `${autoId}-label`

    const [open, setOpen] = useState(false)
    const [active, setActive] = useState(-1)
    const [pos, setPos] = useState<React.CSSProperties>({})
    const buttonRef = useRef<HTMLButtonElement | null>(null)
    const listRef = useRef<HTMLUListElement | null>(null)
    const typed = useRef({ text: '', at: 0 })

    const setRefs = (el: HTMLButtonElement | null) => {
      buttonRef.current = el
      if (typeof ref === 'function') ref(el)
      else if (ref) ref.current = el
    }

    // Fixed positioning in a portal: never clipped by a modal's overflow; flips upwards
    // when there isn't room below.
    const place = useCallback(() => {
      const r = buttonRef.current?.getBoundingClientRect()
      if (!r) return
      const below = window.innerHeight - r.bottom
      const up = below < Math.min(MAX_HEIGHT, 200) && r.top > below
      setPos({
        left: r.left,
        minWidth: r.width,
        maxWidth: Math.max(r.width, 360),
        ...(up ? { bottom: window.innerHeight - r.top + 4 } : { top: r.bottom + 4 }),
        maxHeight: Math.min(MAX_HEIGHT, (up ? r.top : below) - 12),
      })
    }, [])

    const show = () => {
      if (disabled) return
      place()
      setActive(selectedIndex >= 0 ? selectedIndex : firstEnabled(options, 0, 1))
      setOpen(true)
    }
    const hide = (refocus = true) => {
      setOpen(false)
      if (refocus) buttonRef.current?.focus()
    }
    const pick = (i: number) => {
      const o = options[i]
      if (!o || o.disabled) return
      if (o.value !== current) onChange?.({ target: { value: o.value } })
      hide()
    }

    useLayoutEffect(() => {
      if (!open) return
      listRef.current
        ?.querySelector<HTMLElement>(`[data-index="${active}"]`)
        ?.scrollIntoView({ block: 'nearest' })
    }, [open, active])

    useEffect(() => {
      if (!open) return
      const onDown = (e: MouseEvent) => {
        const t = e.target as Node
        if (!buttonRef.current?.contains(t) && !listRef.current?.contains(t)) hide(false)
      }
      const onScroll = (e: Event) => {
        if (!listRef.current?.contains(e.target as Node)) place()
      }
      document.addEventListener('mousedown', onDown)
      window.addEventListener('scroll', onScroll, true)
      window.addEventListener('resize', place)
      return () => {
        document.removeEventListener('mousedown', onDown)
        window.removeEventListener('scroll', onScroll, true)
        window.removeEventListener('resize', place)
      }
    }, [open, place])

    const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
      const move = (from: number, dir: 1 | -1) => {
        e.preventDefault()
        const next = firstEnabled(options, from, dir)
        if (next >= 0) setActive(next)
      }
      if (!open) {
        if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
          e.preventDefault()
          show()
        }
        return
      }
      switch (e.key) {
        case 'ArrowDown':
          return move(active + 1, 1)
        case 'ArrowUp':
          return move(active - 1, -1)
        case 'Home':
          return move(0, 1)
        case 'End':
          return move(options.length - 1, -1)
        case 'Enter':
        case ' ':
          e.preventDefault()
          return pick(active)
        case 'Escape':
          // Close the list only — not the modal that may contain it.
          e.preventDefault()
          e.stopPropagation()
          return hide()
        case 'Tab':
          return hide(false)
        default:
          if (e.key.length === 1) {
            // Type-ahead: jump to the first option starting with what's been typed.
            const now = Date.now()
            typed.current.text =
              (now - typed.current.at < 600 ? typed.current.text : '') + e.key.toLowerCase()
            typed.current.at = now
            const hit = options.findIndex(
              (o) => !o.disabled && o.text.toLowerCase().startsWith(typed.current.text),
            )
            if (hit >= 0) setActive(hit)
          }
      }
    }

    return (
      <div className="block">
        {label && (
          <span id={labelId} className="mb-1.5 block text-[13px] font-medium text-tx-2">
            {label}
          </span>
        )}
        <button
          ref={setRefs}
          id={buttonId}
          type="button"
          disabled={disabled}
          role="combobox"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={open ? listId : undefined}
          aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
          aria-labelledby={label ? `${labelId} ${buttonId}` : undefined}
          aria-label={aria['aria-label']}
          onClick={() => (open ? hide() : show())}
          onKeyDown={onKeyDown}
          className={cn(
            'flex w-full items-center gap-2 text-left text-sm text-tx',
            'disabled:cursor-not-allowed disabled:opacity-50',
            variant === 'default' &&
              'h-10 rounded-lg border border-line bg-bg px-3 focus:border-accent focus:outline-none',
            variant === 'default' && open && 'border-accent',
            variant === 'bare' &&
              'rounded-md focus:outline-none focus-visible:ring-1 focus-visible:ring-accent',
            className,
          )}
        >
          <span className="min-w-0 flex-1 truncate">{selected?.label ?? ' '}</span>
          <ChevronDown
            className={cn('h-4 w-4 shrink-0 text-tx-3 transition-transform', open && 'rotate-180')}
          />
        </button>

        {open &&
          createPortal(
            <ul
              ref={listRef}
              id={listId}
              role="listbox"
              aria-labelledby={label ? labelId : undefined}
              className="fixed z-[100] overflow-y-auto rounded-lg border border-line bg-surface p-1 shadow-lg animate-pop-in"
              style={pos}
            >
              {options.map((o, i) => {
                const isSelected = i === selectedIndex
                return (
                  <li
                    key={`${o.value}-${i}`}
                    id={`${listId}-${i}`}
                    data-index={i}
                    role="option"
                    aria-selected={isSelected}
                    aria-disabled={o.disabled || undefined}
                    // mousedown would blur the button first; keep focus on it.
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => pick(i)}
                    onMouseEnter={() => !o.disabled && setActive(i)}
                    className={cn(
                      'flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-sm',
                      i === active ? 'bg-surface-2 text-tx' : 'text-tx-2',
                      isSelected && 'font-medium text-accent',
                      o.disabled && 'cursor-not-allowed opacity-40',
                    )}
                  >
                    <span className="min-w-0 flex-1 truncate">{o.label}</span>
                    {isSelected && <Check className="h-4 w-4 shrink-0" />}
                  </li>
                )
              })}
            </ul>,
            document.body,
          )}
      </div>
    )
  },
)
Select.displayName = 'Select'

function collectOptions(children: ReactNode): Opt[] {
  const out: Opt[] = []
  Children.forEach(children, (child) => {
    if (!isValidElement(child)) return
    const el = child as ReactElement<{
      value?: string | number
      children?: ReactNode
      disabled?: boolean
    }>
    if (el.type === 'option') {
      const text = textOf(el.props.children)
      out.push({
        value: String(el.props.value ?? text),
        label: el.props.children,
        text,
        disabled: !!el.props.disabled,
      })
    } else if (el.props.children) {
      out.push(...collectOptions(el.props.children)) // fragments / <optgroup>
    }
  })
  return out
}

function textOf(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (isValidElement(node)) return textOf((node.props as { children?: ReactNode }).children)
  return ''
}

/** First enabled option from `from` walking in `dir` (−1 if none). */
function firstEnabled(options: Opt[], from: number, dir: 1 | -1): number {
  for (let i = from; i >= 0 && i < options.length; i += dir) {
    if (!options[i].disabled) return i
  }
  return -1
}
