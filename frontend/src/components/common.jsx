// Small pieces shared by the actuals, TDS, alerts and simulation screens.
export function SubTabs({ tabs, value, onChange }) {
  return (
    <div className="subtabs" role="tablist">
      {tabs.map(([k, l, n]) => (
        <button key={k} role="tab" aria-selected={k === value} onClick={() => onChange(k)}>{l}{n ? <span className="cnt">{n}</span> : null}</button>
      ))}
    </div>
  )
}

export const Kpi = ({ label, value, sub, tone }) => (
  <div className={`kpi ${tone || ''}`}><span>{label}</span><b>{value}</b>{sub && <small>{sub}</small>}</div>
)

export const Badge = ({ tone, children }) => <span className={`badge ${tone || ''}`}>{children}</span>

export const todayIso = () => new Date().toISOString().slice(0, 10)

// FY start for a date: April–March
export const fyOfDate = (d = new Date()) => (d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1)
