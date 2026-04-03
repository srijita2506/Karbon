import { useEffect, useMemo, useState } from 'react'
import './App.css'

const API_ROOT = import.meta.env.VITE_API_ROOT || 'http://127.0.0.1:8000'
const API_BASE = `${API_ROOT}/api`

const emptyExpense = {
  id: null,
  amount: '',
  description: '',
  date: '',
  payerId: '',
  splitMode: 'equal',
  participantIds: [],
  splitValues: {},
}

function App() {
  const [authMode, setAuthMode] = useState('login')
  const [authLoading, setAuthLoading] = useState(false)
  const [authError, setAuthError] = useState('')
  const [token, setToken] = useState(localStorage.getItem('splitmint_token') || '')
  const [user, setUser] = useState(null)

  const [groups, setGroups] = useState([])
  const [activeGroupId, setActiveGroupId] = useState(null)
  const [groupForm, setGroupForm] = useState({ name: '', participants: [] })
  const [groupError, setGroupError] = useState('')
  const [groupNameDraft, setGroupNameDraft] = useState('')

  const [participantsDraft, setParticipantsDraft] = useState([])
  const [summary, setSummary] = useState(null)
  const [balance, setBalance] = useState(null)

  const [expenses, setExpenses] = useState([])
  const [expenseForm, setExpenseForm] = useState(emptyExpense)
  const [expenseError, setExpenseError] = useState('')
  const [mintSenseText, setMintSenseText] = useState('')
  const [mintSenseResult, setMintSenseResult] = useState(null)
  const [mintSenseError, setMintSenseError] = useState('')
  const [mintSenseLoading, setMintSenseLoading] = useState(false)
  const [mintSenseApplied, setMintSenseApplied] = useState(false)

  const [filters, setFilters] = useState({
    search: '',
    participant: '',
    dateFrom: '',
    dateTo: '',
    amountMin: '',
    amountMax: '',
  })

  const activeGroup = useMemo(
    () => groups.find((group) => group.id === activeGroupId) || null,
    [groups, activeGroupId],
  )

  const participantMap = useMemo(() => {
    const map = new Map()
    if (activeGroup?.participants) {
      activeGroup.participants.forEach((participant) => {
        map.set(participant.id, participant.name)
      })
    }
    return map
  }, [activeGroup])

  const contributionChart = useMemo(() => {
    if (!summary?.participants?.length) return []
    const maxPaid = Math.max(
      ...summary.participants.map((participant) => Number(participant.paid || 0)),
      0,
    )
    return summary.participants.map((participant) => ({
      id: participant.participant_id,
      name: participant.name,
      paid: Number(participant.paid || 0),
      share: Number(participant.share || 0),
      paidPct: maxPaid ? Math.round((Number(participant.paid || 0) / maxPaid) * 100) : 0,
      sharePct: maxPaid ? Math.round((Number(participant.share || 0) / maxPaid) * 100) : 0,
    }))
  }, [summary])

  const authHeader = token ? { Authorization: `Bearer ${token}` } : {}

  const apiFetch = async (path, options = {}) => {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...authHeader,
        ...(options.headers || {}),
      },
      ...options,
    })

    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(errorText || 'Request failed')
    }

    if (response.status === 204) {
      return null
    }

    return response.json()
  }

  const loadMe = async () => {
    if (!token) return
    try {
      const payload = await apiFetch('/auth/me/')
      setUser(payload)
    } catch (error) {
      setToken('')
      localStorage.removeItem('splitmint_token')
    }
  }

  const loadGroups = async () => {
    if (!token) return
    const payload = await apiFetch('/groups/')
    setGroups(payload)
    if (!activeGroupId && payload.length) {
      setActiveGroupId(payload[0].id)
    }
  }

  const loadSummary = async (groupId) => {
    if (!groupId) return
    const payload = await apiFetch(`/groups/${groupId}/summary/`)
    setSummary(payload)
  }

  const loadBalance = async (groupId) => {
    if (!groupId) return
    const payload = await apiFetch(`/groups/${groupId}/balance/`)
    setBalance(payload)
  }

  const loadExpenses = async (groupId) => {
    if (!groupId) return
    const params = new URLSearchParams()
    params.set('group', groupId)
    if (filters.search) params.set('search', filters.search)
    if (filters.participant) params.set('participant', filters.participant)
    if (filters.dateFrom) params.set('date_from', filters.dateFrom)
    if (filters.dateTo) params.set('date_to', filters.dateTo)
    if (filters.amountMin) params.set('amount_min', filters.amountMin)
    if (filters.amountMax) params.set('amount_max', filters.amountMax)
    const payload = await apiFetch(`/expenses/?${params.toString()}`)
    setExpenses(payload)
  }

  useEffect(() => {
    loadMe()
  }, [token])

  useEffect(() => {
    if (token) {
      loadGroups()
    }
  }, [token])

  useEffect(() => {
    if (activeGroupId) {
      loadSummary(activeGroupId)
      loadBalance(activeGroupId)
      loadExpenses(activeGroupId)
    }
  }, [activeGroupId])

  useEffect(() => {
    if (activeGroupId) {
      loadExpenses(activeGroupId)
    }
  }, [filters])

  useEffect(() => {
    if (activeGroup?.participants) {
      setGroupNameDraft(activeGroup.name)
      const nonPrimary = activeGroup.participants.filter((p) => !p.is_primary)
      setParticipantsDraft(
        nonPrimary.map((participant) => ({
          id: participant.id,
          name: participant.name,
          color: participant.color || '',
          avatar: participant.avatar || '',
        })),
      )
    }
  }, [activeGroup])

  const handleAuth = async (event) => {
    event.preventDefault()
    setAuthError('')
    setAuthLoading(true)

    const form = new FormData(event.target)
    const payload = Object.fromEntries(form.entries())

    try {
      const endpoint = authMode === 'login' ? '/auth/login/' : '/auth/register/'
      const data = await apiFetch(endpoint, {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      localStorage.setItem('splitmint_token', data.access)
      setToken(data.access)
    } catch (error) {
      setAuthError(error.message)
    } finally {
      setAuthLoading(false)
    }
  }

  const handleLogout = () => {
    setToken('')
    setUser(null)
    setGroups([])
    setActiveGroupId(null)
    localStorage.removeItem('splitmint_token')
  }

  const handleCreateGroup = async (event) => {
    event.preventDefault()
    setGroupError('')
    try {
      const payload = {
        name: groupForm.name,
        participants: groupForm.participants.filter((p) => p.name.trim()),
      }
      await apiFetch('/groups/', { method: 'POST', body: JSON.stringify(payload) })
      setGroupForm({ name: '', participants: [] })
      await loadGroups()
    } catch (error) {
      setGroupError(error.message)
    }
  }

  const handleUpdateGroup = async () => {
    if (!activeGroup) return
    setGroupError('')
    try {
      const payload = {
        name: groupNameDraft,
        participants: participantsDraft.filter((p) => p.name.trim()),
      }
      await apiFetch(`/groups/${activeGroup.id}/`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
      await loadGroups()
    } catch (error) {
      setGroupError(error.message)
    }
  }

  const handleDeleteGroup = async () => {
    if (!activeGroup) return
    if (!window.confirm('Delete this group and all its data?')) return
    await apiFetch(`/groups/${activeGroup.id}/`, { method: 'DELETE' })
    await loadGroups()
    setActiveGroupId(null)
  }

  const handleExportCsv = async () => {
    if (!activeGroup) return
    try {
      const response = await fetch(`${API_BASE}/groups/${activeGroup.id}/export/`, {
        headers: {
          ...authHeader,
        },
      })
      if (!response.ok) {
        throw new Error('Export failed')
      }
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `splitmint_${activeGroup.id}.csv`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (error) {
      setGroupError(error.message)
    }
  }

  const updateParticipantDraft = (index, field, value) => {
    setParticipantsDraft((prev) =>
      prev.map((item, idx) => (idx === index ? { ...item, [field]: value } : item)),
    )
  }

  const addDraftParticipant = () => {
    if (participantsDraft.length >= 3) return
    setParticipantsDraft((prev) => [...prev, { name: '', color: '', avatar: '' }])
  }

  const removeDraftParticipant = (index) => {
    setParticipantsDraft((prev) => prev.filter((_, idx) => idx !== index))
  }

  const handleExpenseFormChange = (field, value) => {
    setExpenseForm((prev) => ({ ...prev, [field]: value }))
  }

  const toggleExpenseParticipant = (participantId) => {
    setExpenseForm((prev) => {
      const exists = prev.participantIds.includes(participantId)
      const nextIds = exists
        ? prev.participantIds.filter((id) => id !== participantId)
        : [...prev.participantIds, participantId]
      return { ...prev, participantIds: nextIds }
    })
  }

  const handleSplitValue = (participantId, value) => {
    setExpenseForm((prev) => ({
      ...prev,
      splitValues: { ...prev.splitValues, [participantId]: value },
    }))
  }

  const resetExpenseForm = () => {
    setExpenseForm({ ...emptyExpense, date: new Date().toISOString().slice(0, 10) })
    setExpenseError('')
  }

  useEffect(() => {
    if (activeGroup?.participants?.length) {
      const defaultIds = activeGroup.participants.map((p) => p.id)
      setExpenseForm((prev) => ({
        ...prev,
        participantIds: prev.participantIds.length ? prev.participantIds : defaultIds,
        payerId: prev.payerId || activeGroup.participants[0].id,
        date: prev.date || new Date().toISOString().slice(0, 10),
      }))
    }
  }, [activeGroup])

  const buildSplits = () => {
    if (expenseForm.splitMode === 'equal') {
      return expenseForm.participantIds.map((id) => ({ participant_id: id }))
    }
    if (expenseForm.splitMode === 'amount') {
      return expenseForm.participantIds.map((id) => ({
        participant_id: id,
        amount: expenseForm.splitValues[id] || 0,
      }))
    }
    return expenseForm.participantIds.map((id) => ({
      participant_id: id,
      percentage: expenseForm.splitValues[id] || 0,
    }))
  }

  const handleSaveExpense = async (event) => {
    event.preventDefault()
    if (!activeGroup) return
    setExpenseError('')
    try {
      if (!expenseForm.payerId) {
        setExpenseError('Please select who paid for this expense.')
        return
      }
      if (!expenseForm.participantIds.length) {
        setExpenseError('Please select at least one participant.')
        return
      }
      const payload = {
        group: activeGroup.id,
        payer: Number(expenseForm.payerId),
        amount: expenseForm.amount,
        description: expenseForm.description,
        date: expenseForm.date,
        split_mode: expenseForm.splitMode,
        splits: buildSplits(),
      }

      if (expenseForm.id) {
        await apiFetch(`/expenses/${expenseForm.id}/`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
      } else {
        await apiFetch('/expenses/', { method: 'POST', body: JSON.stringify(payload) })
      }

      resetExpenseForm()
      await loadSummary(activeGroup.id)
      await loadBalance(activeGroup.id)
      await loadExpenses(activeGroup.id)
    } catch (error) {
      setExpenseError(error.message)
    }
  }

  const handleEditExpense = (expense) => {
    const participantIds = expense.splits.map((split) => split.participant_id)
    const splitValues = {}
    expense.splits.forEach((split) => {
      if (expense.split_mode === 'amount') splitValues[split.participant_id] = split.amount
      if (expense.split_mode === 'percent') splitValues[split.participant_id] = split.percentage
    })
    setExpenseForm({
      id: expense.id,
      amount: expense.amount,
      description: expense.description,
      date: expense.date,
      payerId: expense.payer,
      splitMode: expense.split_mode,
      participantIds,
      splitValues,
    })
  }

  const handleDeleteExpense = async (expenseId) => {
    if (!window.confirm('Delete this expense?')) return
    await apiFetch(`/expenses/${expenseId}/`, { method: 'DELETE' })
    await loadSummary(activeGroupId)
    await loadBalance(activeGroupId)
    await loadExpenses(activeGroupId)
  }

  const handleMintSense = async () => {
    if (!mintSenseText.trim()) return
    setMintSenseError('')
    setMintSenseLoading(true)
    setMintSenseApplied(false)
    try {
      const payload = await apiFetch('/mintsense/', {
        method: 'POST',
        body: JSON.stringify({ text: mintSenseText, group_id: activeGroupId }),
      })
      setMintSenseResult(payload)
    } catch (error) {
      setMintSenseError(error.message)
    } finally {
      setMintSenseLoading(false)
    }
  }

  const applyMintSense = () => {
    if (!mintSenseResult || !activeGroup) return
    const participantIds = mintSenseResult.participant_ids
      ? mintSenseResult.participant_ids.map((id) => Number(id))
      : null
    const splitValues = {}
    if (mintSenseResult.split_values) {
      Object.entries(mintSenseResult.split_values).forEach(([key, value]) => {
        splitValues[Number(key)] = value
      })
    }
    const nextSplitMode = mintSenseResult.split_values
      ? 'percent'
      : mintSenseResult.split_mode
    setExpenseForm((prev) => ({
      ...prev,
      amount: mintSenseResult.amount,
      description: mintSenseResult.description,
      date: mintSenseResult.date,
      splitMode: nextSplitMode,
      payerId: mintSenseResult.payer_id || prev.payerId,
      participantIds: participantIds || prev.participantIds,
      splitValues: Object.keys(splitValues).length ? splitValues : prev.splitValues,
    }))
    setMintSenseApplied(true)
  }

  if (!token) {
    return (
      <div className="page">
        <section className="hero">
          <div>
            <p className="tag">SplitMint</p>
            <h1>Your Gateway to Karbon</h1>
            <p className="subtext">
              Welcome back! Track shared expenses, see who owes whom, and keep every group synced
              with fresh summaries and clean settlements.
            </p>
          </div>
          <div className="badge">MintSense-ready</div>
        </section>

        <div className="grid">
          <div className="panel">
            <div className="panel-header">
              <h2>{authMode === 'login' ? 'Sign in' : 'Create account'}</h2>
              <div className="segmented">
                <button
                  className={authMode === 'login' ? 'active' : ''}
                  type="button"
                  onClick={() => setAuthMode('login')}
                >
                  Login
                </button>
                <button
                  className={authMode === 'register' ? 'active' : ''}
                  type="button"
                  onClick={() => setAuthMode('register')}
                >
                  Register
                </button>
              </div>
            </div>
            <form className="stack" onSubmit={handleAuth}>
              <input type="email" name="email" placeholder="Email" required />
              <input type="password" name="password" placeholder="Password" required />
              {authMode === 'register' && (
                <>
                  <input type="password" name="password_confirm" placeholder="Confirm password" required />
                  <input type="text" name="first_name" placeholder="First name" />
                  <input type="text" name="last_name" placeholder="Last name" />
                </>
              )}
              {authError && <div className="error">{authError}</div>}
              <button className="primary" type="submit" disabled={authLoading}>
                {authLoading ? 'Loading…' : authMode === 'login' ? 'Login' : 'Create account'}
              </button>
            </form>
          </div>

          <div className="panel">
            <h2>What you can do</h2>
            <div className="stack">
              <div className="user-card">
                <strong>Track groups</strong>
                <span className="muted">Up to 3 participants plus you, with per-person totals.</span>
              </div>
              <div className="user-card">
                <strong>Balance engine</strong>
                <span className="muted">See who owes whom with minimal settlements.</span>
              </div>
              <div className="user-card">
                <strong>Filters & search</strong>
                <span className="muted">Find expenses by date, person, or keyword.</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <section className="hero">
        <div>
          <p className="tag">SplitMint workspace</p>
          <h1>Hello {user?.first_name || user?.email || 'there'}, let’s keep things even.</h1>
          <p className="subtext">
            Switch groups, track expenses, and generate instant settlements.
          </p>
        </div>
        <div className="row">
          <button className="secondary" type="button" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </section>

      <div className="grid">
        <div className="panel">
          <div className="panel-header">
            <h2>Your groups</h2>
            <button className="secondary" type="button" onClick={() => setGroupForm({ name: '', participants: [] })}>
              New group
            </button>
          </div>
          <div className="group-grid">
            {groups.map((group) => (
              <button
                key={group.id}
                className={`group-card ${activeGroupId === group.id ? 'active' : ''}`}
                type="button"
                onClick={() => setActiveGroupId(group.id)}
              >
                <strong>{group.name}</strong>
                <div className="muted">{group.participants.length} members</div>
              </button>
            ))}
            {!groups.length && <div className="empty">No groups yet. Create one below.</div>}
          </div>

          <form className="stack" onSubmit={handleCreateGroup}>
            <input
              type="text"
              placeholder="Group name"
              value={groupForm.name}
              onChange={(event) => setGroupForm((prev) => ({ ...prev, name: event.target.value }))}
              required
            />
            <div className="stack">
              {(groupForm.participants || []).map((participant, index) => (
                <div className="row" key={`new-${index}`}>
                  <input
                    type="text"
                    placeholder="Participant name"
                    value={participant.name}
                    onChange={(event) => {
                      const value = event.target.value
                      setGroupForm((prev) => ({
                        ...prev,
                        participants: prev.participants.map((p, idx) =>
                          idx === index ? { ...p, name: value } : p,
                        ),
                      }))
                    }}
                  />
                  <button
                    className="ghost"
                    type="button"
                    onClick={() =>
                      setGroupForm((prev) => ({
                        ...prev,
                        participants: prev.participants.filter((_, idx) => idx !== index),
                      }))
                    }
                  >
                    Remove
                  </button>
                </div>
              ))}
              {groupForm.participants.length < 3 && (
                <button
                  className="secondary"
                  type="button"
                  onClick={() =>
                    setGroupForm((prev) => ({
                      ...prev,
                      participants: [...prev.participants, { name: '' }],
                    }))
                  }
                >
                  Add participant
                </button>
              )}
            </div>
            {groupError && <div className="error">{groupError}</div>}
            <button className="primary" type="submit">
              Create group
            </button>
          </form>
        </div>

        <div className="panel wide">
          {activeGroup ? (
            <div className="stack">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Active group</p>
                  <input
                    type="text"
                    value={groupNameDraft}
                    onChange={(event) => setGroupNameDraft(event.target.value)}
                  />
                </div>
                <div className="row">
                  <button className="secondary" type="button" onClick={handleExportCsv}>
                    Export CSV
                  </button>
                  <button className="ghost" type="button" onClick={handleDeleteGroup}>
                    Delete group
                  </button>
                </div>
              </div>

              {summary && (
                <div className="balance-grid">
                  <div className="user-card">
                    <div className="eyebrow">Total spent</div>
                    <h3>₹ {summary.total_spent}</h3>
                  </div>
                  <div className="user-card">
                    <div className="eyebrow">You owe</div>
                    <h3>₹ {summary.owed_by_user}</h3>
                  </div>
                  <div className="user-card">
                    <div className="eyebrow">Owed to you</div>
                    <h3>₹ {summary.owed_to_user}</h3>
                  </div>
                </div>
              )}

              <div className="panel">
                <div className="panel-header">
                  <h3>Participants</h3>
                  <button className="secondary" type="button" onClick={addDraftParticipant}>
                    Add participant
                  </button>
                </div>
                <div className="stack">
                  {participantsDraft.map((participant, index) => (
                    <div className="row" key={`draft-${index}`}>
                      <input
                        type="text"
                        placeholder="Name"
                        value={participant.name}
                        onChange={(event) => updateParticipantDraft(index, 'name', event.target.value)}
                      />
                      <input
                        type="text"
                        placeholder="Color"
                        value={participant.color}
                        onChange={(event) => updateParticipantDraft(index, 'color', event.target.value)}
                      />
                      <input
                        type="text"
                        placeholder="Avatar url"
                        value={participant.avatar}
                        onChange={(event) => updateParticipantDraft(index, 'avatar', event.target.value)}
                      />
                      <button className="ghost" type="button" onClick={() => removeDraftParticipant(index)}>
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
                <button className="primary" type="button" onClick={handleUpdateGroup}>
                  Save participants
                </button>
              </div>

              {summary && (
                <div className="panel">
                  <div className="panel-header">
                    <h3>Contributions</h3>
                  </div>
                  <div className="list">
                    {summary.participants.map((participant) => (
                      <div className="list-item" key={`contrib-${participant.participant_id}`}>
                        <div>
                          <strong>{participant.name}</strong>
                          <div className="muted">Paid ₹ {participant.paid}</div>
                        </div>
                        <div className="pill">Share ₹ {participant.share}</div>
                        <div className="pill">Net ₹ {participant.balance}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {summary && (
                <div className="panel">
                  <div className="panel-header">
                    <h3>Group dashboard</h3>
                  </div>
                  <div className="stack">
                    {contributionChart.map((row) => (
                      <div className="chart-row" key={`chart-${row.id}`}>
                        <div className="chart-label">
                          <strong>{row.name}</strong>
                          <span className="muted">Paid ₹ {row.paid.toFixed(2)}</span>
                        </div>
                        <div className="chart-bars">
                          <div className="chart-bar paid" style={{ width: `${row.paidPct}%` }} />
                          <div className="chart-bar share" style={{ width: `${row.sharePct}%` }} />
                        </div>
                        <span className="muted">Share ₹ {row.share.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                  <div className="row">
                    <span className="pill">Paid</span>
                    <span className="pill">Share</span>
                  </div>
                </div>
              )}

              {balance && (
                <div className="panel">
                  <div className="panel-header">
                    <h3>Settlement suggestions</h3>
                  </div>
                  {balance.balances && (
                    <div className="stack">
                      {balance.balances.map((entry) => {
                        const value = Number(entry.balance)
                        const tone = value > 0 ? 'positive' : value < 0 ? 'negative' : ''
                        return (
                          <div className={`balance-row ${tone}`} key={`bal-${entry.participant_id}`}>
                            <span>{participantMap.get(entry.participant_id) || `Participant ${entry.participant_id}`}</span>
                            <strong>₹ {entry.balance}</strong>
                          </div>
                        )
                      })}
                    </div>
                  )}
                  {balance.settlements.length ? (
                    <div className="stack">
                      {balance.settlements.map((settlement, index) => (
                        <div className="balance-row" key={`settle-${index}`}>
                          <span>{settlement.from_name || participantMap.get(settlement.from_participant_id) || 'Participant'}</span>
                          <span>→</span>
                          <span>{settlement.to_name || participantMap.get(settlement.to_participant_id) || 'Participant'}</span>
                          <strong>₹ {settlement.amount}</strong>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="empty">All settled up.</div>
                  )}
                </div>
              )}

              <div className="panel">
                <div className="panel-header">
                  <h3>Log expense</h3>
                  {expenseForm.id && (
                    <button className="ghost" type="button" onClick={resetExpenseForm}>
                      Cancel edit
                    </button>
                  )}
                </div>
                <form className="stack" onSubmit={handleSaveExpense}>
                  <div className="row">
                    <input
                      type="number"
                      step="0.01"
                      placeholder="Amount"
                      value={expenseForm.amount}
                      onChange={(event) => handleExpenseFormChange('amount', event.target.value)}
                      required
                    />
                    <input
                      type="date"
                      value={expenseForm.date}
                      onChange={(event) => handleExpenseFormChange('date', event.target.value)}
                      required
                    />
                  </div>
                  <input
                    type="text"
                    placeholder="Description"
                    value={expenseForm.description}
                    onChange={(event) => handleExpenseFormChange('description', event.target.value)}
                  />
                  <div className="row">
                    <label className="muted">Paid by</label>
                    <select
                      value={expenseForm.payerId || ''}
                      onChange={(event) => handleExpenseFormChange('payerId', event.target.value)}
                    >
                      <option value="" disabled>
                        Select payer
                      </option>
                      {activeGroup.participants.map((participant) => (
                        <option key={`payer-${participant.id}`} value={participant.id}>
                          {participant.name}
                        </option>
                      ))}
                    </select>
                    <select
                      value={expenseForm.splitMode}
                      onChange={(event) => handleExpenseFormChange('splitMode', event.target.value)}
                    >
                      <option value="equal">Equal</option>
                      <option value="amount">Custom amount</option>
                      <option value="percent">Percentage</option>
                    </select>
                  </div>

                  <div className="stack">
                    {activeGroup.participants.map((participant) => (
                      <div className="row" key={`split-${participant.id}`}>
                        <label>
                          <input
                            type="checkbox"
                            checked={expenseForm.participantIds.includes(participant.id)}
                            onChange={() => toggleExpenseParticipant(participant.id)}
                          />
                          {participant.name}
                        </label>
                        {expenseForm.splitMode !== 'equal' && expenseForm.participantIds.includes(participant.id) && (
                          <input
                            type="number"
                            step="0.01"
                            placeholder={expenseForm.splitMode === 'amount' ? 'Amount' : 'Percent'}
                            value={expenseForm.splitValues[participant.id] || ''}
                            onChange={(event) => handleSplitValue(participant.id, event.target.value)}
                          />
                        )}
                      </div>
                    ))}
                  </div>

                  {expenseError && <div className="error">{expenseError}</div>}
                  <button className="primary" type="submit">
                    {expenseForm.id ? 'Update expense' : 'Add expense'}
                  </button>
                </form>
              </div>

              <div className="panel">
                <div className="panel-header">
                  <h3>Expenses</h3>
                </div>
                <div className="row">
                  <input
                    type="text"
                    placeholder="Search description"
                    value={filters.search}
                    onChange={(event) => setFilters((prev) => ({ ...prev, search: event.target.value }))}
                  />
                  <select
                    value={filters.participant}
                    onChange={(event) => setFilters((prev) => ({ ...prev, participant: event.target.value }))}
                  >
                    <option value="">All participants</option>
                    {activeGroup.participants.map((participant) => (
                      <option key={`filter-${participant.id}`} value={participant.id}>
                        {participant.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="row">
                  <input
                    type="date"
                    value={filters.dateFrom}
                    onChange={(event) => setFilters((prev) => ({ ...prev, dateFrom: event.target.value }))}
                  />
                  <input
                    type="date"
                    value={filters.dateTo}
                    onChange={(event) => setFilters((prev) => ({ ...prev, dateTo: event.target.value }))}
                  />
                </div>
                <div className="row">
                  <input
                    type="number"
                    placeholder="Min amount"
                    value={filters.amountMin}
                    onChange={(event) => setFilters((prev) => ({ ...prev, amountMin: event.target.value }))}
                  />
                  <input
                    type="number"
                    placeholder="Max amount"
                    value={filters.amountMax}
                    onChange={(event) => setFilters((prev) => ({ ...prev, amountMax: event.target.value }))}
                  />
                </div>

                <div className="list">
                  {expenses.length ? (
                    expenses.map((expense) => (
                      <div className="list-item" key={`expense-${expense.id}`}>
                        <div>
                          <strong>{expense.description || 'Untitled expense'}</strong>
                          <div className="muted">₹ {expense.amount} • {expense.date}</div>
                        </div>
                        <div className="row">
                          <button className="secondary" type="button" onClick={() => handleEditExpense(expense)}>
                            Edit
                          </button>
                          <button className="ghost" type="button" onClick={() => handleDeleteExpense(expense.id)}>
                            Delete
                          </button>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="empty">No expenses found.</div>
                  )}
                </div>
              </div>

              <div className="panel">
                <div className="panel-header">
                  <h3>MintSense</h3>
                </div>
                <div className="stack">
                  <textarea
                    className="textarea"
                    rows="4"
                    placeholder="e.g. I paid 1200 for groceries yesterday split equally"
                    value={mintSenseText}
                    onChange={(event) => setMintSenseText(event.target.value)}
                  />
                  <div className="row">
                    <button className="secondary" type="button" onClick={handleMintSense} disabled={mintSenseLoading}>
                      {mintSenseLoading ? 'Parsing…' : 'Generate draft'}
                    </button>
                    {mintSenseResult && (
                      <button className="primary" type="button" onClick={applyMintSense}>
                        Apply to expense form
                      </button>
                    )}
                  </div>
                  {mintSenseError && <div className="error">{mintSenseError}</div>}
                  {mintSenseApplied && (
                    <div className="user-card">
                      <strong>Applied to expense form</strong>
                      <span className="muted">Scroll to the expense form to review and save.</span>
                    </div>
                  )}
                  {mintSenseResult && (
                    <div className="user-card">
                      <strong>Draft</strong>
                      <div className="muted">Amount: ₹ {mintSenseResult.amount}</div>
                      <div className="muted">Description: {mintSenseResult.description}</div>
                      <div className="muted">Date: {mintSenseResult.date}</div>
                      <div className="muted">Split: {mintSenseResult.split_mode}</div>
                      {mintSenseResult.payer_id && (
                        <div className="muted">
                          Payer: {participantMap.get(mintSenseResult.payer_id) || `#${mintSenseResult.payer_id}`}
                        </div>
                      )}
                      {mintSenseResult.participant_ids && (
                        <div className="muted">
                          Participants: {mintSenseResult.participant_ids.length}
                        </div>
                      )}
                      {mintSenseResult.split_values && (
                        <div className="muted">
                          Split values provided
                        </div>
                      )}
                      <div className="stack">
                        {mintSenseResult.suggestions.map((item, index) => (
                          <span className="pill" key={`suggest-${index}`}>
                            {item}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="empty">Select a group to get started.</div>
          )}
        </div>
      </div>
    </div>
  )
}

export default App
