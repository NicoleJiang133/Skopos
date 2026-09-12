import { useState, type ChangeEvent, type FormEvent } from 'react'
import type { ScanResult } from '../backend/handoff'
import type { VenueInventory } from '../state/schema'

const VENUE_TYPES: VenueInventory['venueType'][] = [
  'cafe',
  'restaurant',
  'bar',
  'office',
  'retail',
  'warehouse',
  'home',
  'other',
]

const PEAK_HOURS: VenueInventory['peakHour'][] = ['morning', 'lunch', 'afternoon', 'dinner', 'late']

type FormValues = {
  venueType: VenueInventory['venueType']
  tables: string
  chairs: string
  capacity: string
  areaSqm: string
  zones: string
  staffOnShift: string
  peakHour: VenueInventory['peakHour']
  notes: string
}

export function InventoryForm({
  objects,
  scanned,
  onBack,
  onSubmit,
}: {
  objects: ScanResult['objects']
  scanned: boolean
  onBack: () => void
  onSubmit: (inventory: VenueInventory) => void
}) {
  const tableCount = objects.filter((object) =>
    /table|desk|counter|bar\b/i.test(object.label),
  ).length
  const chairCount = objects.filter((object) =>
    /chair|sofa|couch|stool|bench/i.test(object.label),
  ).length
  const [values, setValues] = useState<FormValues>({
    venueType: 'cafe',
    tables: scanned ? String(tableCount) : '',
    chairs: scanned ? String(chairCount) : '',
    capacity: scanned && chairCount > 0 ? String(chairCount) : '',
    areaSqm: '',
    zones: '1',
    staffOnShift: '',
    peakHour: 'lunch',
    notes: '',
  })
  const [error, setError] = useState('')

  const update =
    (key: keyof FormValues) =>
    (event: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
      setValues((previous) => ({ ...previous, [key]: event.target.value }))
      if (error) setError('')
    }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const required = ['tables', 'chairs', 'capacity', 'zones'] as const
    const parsed = Object.fromEntries(
      required.map((key) => [key, values[key].trim() === '' ? null : Number(values[key])]),
    ) as Record<(typeof required)[number], number | null>
    const invalid = required.find(
      (key) => parsed[key] === null || !Number.isFinite(parsed[key]) || parsed[key] < 0,
    )
    if (invalid) {
      setError('Enter non-negative numbers for tables, chairs, capacity, and zones.')
      return
    }

    onSubmit({
      venueType: values.venueType,
      tables: parsed.tables!,
      chairs: parsed.chairs!,
      capacity: parsed.capacity!,
      areaSqm: numberOrZero(values.areaSqm),
      zones: parsed.zones!,
      staffOnShift: numberOrZero(values.staffOnShift),
      peakHour: values.peakHour,
      notes: values.notes.trim(),
    })
  }

  return (
    <form className="sk-panel" style={card} onSubmit={submit}>
      <div style={eyebrow}>JOURNEY COMPLETE</div>
      <div style={title}>Your venue, by the numbers</div>
      <div style={sub}>
        Correct what the scan guessed — this is what your robot will plan against.
      </div>
      <div style={fields}>
        <Field label="Venue type">
          <select
            value={values.venueType}
            onChange={update('venueType')}
            onFocus={focusInput}
            onBlur={blurInput}
            style={input}
          >
            {VENUE_TYPES.map((venueType) => (
              <option key={venueType} value={venueType}>
                {venueType}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Peak hour">
          <select
            value={values.peakHour}
            onChange={update('peakHour')}
            onFocus={focusInput}
            onBlur={blurInput}
            style={input}
          >
            {PEAK_HOURS.map((peakHour) => (
              <option key={peakHour} value={peakHour}>
                {peakHour}
              </option>
            ))}
          </select>
        </Field>
        <NumberField
          label="Tables"
          value={values.tables}
          onChange={update('tables')}
          fromScan={scanned}
        />
        <NumberField
          label="Chairs / seats"
          value={values.chairs}
          onChange={update('chairs')}
          fromScan={scanned}
        />
        <NumberField
          label="Seating capacity (guests)"
          value={values.capacity}
          onChange={update('capacity')}
          fromScan={scanned && chairCount > 0}
        />
        <NumberField
          label="Floor area (m²)"
          value={values.areaSqm}
          onChange={update('areaSqm')}
          step="0.1"
        />
        <NumberField label="Zones / rooms" value={values.zones} onChange={update('zones')} />
        <NumberField
          label="Staff on shift"
          value={values.staffOnShift}
          onChange={update('staffOnShift')}
        />
        <Field label="Notes" fullWidth>
          <textarea
            value={values.notes}
            onChange={update('notes')}
            onFocus={focusInput}
            onBlur={blurInput}
            placeholder="Anything the robot should know — narrow aisles, steps, outdoor seating…"
            style={{ ...input, minHeight: 64, resize: 'vertical' }}
          />
        </Field>
      </div>
      {error && <div style={errorStyle}>{error}</div>}
      <div style={actions}>
        <button type="submit" style={summaryPrimary}>
          Confirm &amp; end journey
        </button>
        <button type="button" onClick={onBack} style={summarySecondary}>
          Back to landing
        </button>
      </div>
    </form>
  )
}

function Field({
  label,
  children,
  fullWidth = false,
}: {
  label: string
  children: React.ReactNode
  fullWidth?: boolean
}) {
  return (
    <label style={{ ...field, ...(fullWidth ? fullWidthField : {}) }}>
      <span style={labelStyle}>{label}</span>
      {children}
    </label>
  )
}

function NumberField({
  label,
  value,
  onChange,
  fromScan = false,
  step = '1',
}: {
  label: string
  value: string
  onChange: (event: ChangeEvent<HTMLInputElement>) => void
  fromScan?: boolean
  step?: string
}) {
  return (
    <Field label={label}>
      <input
        type="number"
        min="0"
        step={step}
        value={value}
        onChange={onChange}
        onFocus={focusInput}
        onBlur={blurInput}
        style={input}
      />
      {fromScan && <span style={helper}>from scan</span>}
    </Field>
  )
}

function numberOrZero(value: string) {
  const number = Number(value)
  return value.trim() === '' || !Number.isFinite(number) ? 0 : Math.max(0, number)
}

function focusInput(
  event: React.FocusEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
) {
  event.currentTarget.style.borderColor = 'var(--sk-cyan)'
}

function blurInput(
  event: React.FocusEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
) {
  event.currentTarget.style.borderColor = 'var(--sk-edge)'
}

const card = {
  width: 'min(520px, calc(100% - 40px))',
  maxHeight: 'calc(100% - 40px)',
  overflowY: 'auto' as const,
  padding: 20,
  zIndex: 4,
  animation: 'sk-rise 420ms var(--sk-ease) both',
}
const eyebrow = {
  color: 'var(--sk-cyan)',
  font: '11px var(--sk-font-mono)',
  letterSpacing: 2,
  marginBottom: 8,
}
const title = {
  color: 'var(--sk-text)',
  font: '22px var(--sk-font-display)',
}
const sub = {
  marginTop: 7,
  color: 'var(--sk-text-dim)',
  font: '12px var(--sk-font-mono)',
  lineHeight: 1.4,
}
const fields = {
  display: 'grid',
  gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
  gap: '12px 10px',
  marginTop: 18,
}
const field = {
  display: 'flex',
  flexDirection: 'column' as const,
  gap: 5,
  minWidth: 0,
}
const fullWidthField = {
  gridColumn: '1 / -1',
}
const labelStyle = {
  color: 'var(--sk-text-dim)',
  font: '11px var(--sk-font-mono)',
}
const input = {
  width: '100%',
  boxSizing: 'border-box' as const,
  background: 'color-mix(in srgb, var(--sk-void) 60%, transparent)',
  border: '1px solid var(--sk-edge)',
  borderRadius: 'var(--sk-radius-sm)',
  color: 'var(--sk-text)',
  padding: '8px 10px',
  font: '14px var(--sk-font-display)',
  outline: 'none',
}
const helper = {
  color: 'var(--sk-text-dim)',
  font: '11px var(--sk-font-mono)',
}
const errorStyle = {
  marginTop: 12,
  color: 'var(--sk-amber)',
  font: '11px var(--sk-font-mono)',
}
const actions = {
  display: 'flex',
  flexDirection: 'column' as const,
  gap: 8,
  marginTop: 18,
}
const summaryPrimary = {
  border: '1px solid var(--sk-cyan)',
  background: 'color-mix(in srgb, var(--sk-cyan) 12%, transparent)',
  color: 'var(--sk-cyan)',
  padding: '11px 14px',
  font: '14px var(--sk-font-display)',
  cursor: 'pointer',
  textAlign: 'left' as const,
}
const summarySecondary = {
  border: '1px solid var(--sk-edge)',
  background: 'transparent',
  color: 'var(--sk-text)',
  padding: '10px 14px',
  font: '13px var(--sk-font-display)',
  cursor: 'pointer',
  textAlign: 'left' as const,
}
