import React, { useEffect, useState } from 'react';
import { Users, UserPlus, Phone, Shield, Lock, Unlock, UserX } from 'lucide-react';
import { apiFetch } from '../../api/emergencyApi';

export function ResidentsPanel() {
  const [residents, setResidents] = useState([]);
  const [nodes, setNodes] = useState([]);
  const [selectedResident, setSelectedResident] = useState(null);
  const [contacts, setContacts] = useState([]);
  const [safetyAuthorized, setSafetyAuthorized] = useState(false);
  const [safetyNote, setSafetyNote] = useState(null);
  const [error, setError] = useState('');

  // Resident registration form
  const [resForm, setResForm] = useState({
    full_name: '',
    age: '',
    address_location: '',
    associated_node_id: '',
    safety_information: '',
    consent_status: 'GRANTED',
  });

  // Contact form
  const [cntForm, setCntForm] = useState({
    full_name: '',
    phone_number: '+91',
    relationship: '',
    priority: 1,
    sms: true,
    voice: true,
    consent_status: 'GRANTED',
  });

  const loadAll = async () => {
    try {
      const [resList, nodeList] = await Promise.all([
        apiFetch('/api/v1/emergency/residents'),
        apiFetch('/api/v1/emergency/nodes'),
      ]);
      setResidents(resList || []);
      setNodes(nodeList || []);
      setError('');
    } catch (err) {
      setError(err.message);
    }
  };

  const loadContacts = async (residentId) => {
    try {
      const list = await apiFetch(
        `/api/v1/emergency/residents/${encodeURIComponent(residentId)}/contacts`
      );
      setContacts(list || []);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    if (selectedResident) {
      loadContacts(selectedResident.resident_id);
      setSafetyNote(null);
      setSafetyAuthorized(false);
    } else {
      setContacts([]);
    }
  }, [selectedResident]);

  const handleCreateResident = async (e) => {
    e.preventDefault();
    setError('');
    try {
      await apiFetch('/api/v1/emergency/residents', {
        method: 'POST',
        body: JSON.stringify({
          full_name: resForm.full_name,
          age: resForm.age ? Number(resForm.age) : null,
          address_location: resForm.address_location,
          associated_node_id: resForm.associated_node_id || null,
          safety_information: resForm.safety_information || null,
          consent_status: resForm.consent_status,
        }),
      });
      setResForm({
        full_name: '',
        age: '',
        address_location: '',
        associated_node_id: '',
        safety_information: '',
        consent_status: 'GRANTED',
      });
      await loadAll();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDeactivateResident = async (residentId) => {
    if (!window.confirm(`Deactivate resident ${residentId}? Historical events remain preserved.`)) return;
    try {
      await apiFetch(`/api/v1/emergency/residents/${encodeURIComponent(residentId)}/deactivate`, {
        method: 'POST',
      });
      if (selectedResident?.resident_id === residentId) setSelectedResident(null);
      await loadAll();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleViewSafetyInfo = async (residentId) => {
    try {
      const data = await apiFetch(
        `/api/v1/emergency/residents/${encodeURIComponent(residentId)}?include_safety_info=true`,
        { headers: { 'X-Navos-Safety-Access': 'authorized' } }
      );
      setSafetyNote(data.safety_information || '(No safety notes recorded)');
      setSafetyAuthorized(true);
    } catch (err) {
      setError(`Safety info restricted: ${err.message}`);
    }
  };

  const handleCreateContact = async (e) => {
    e.preventDefault();
    if (!selectedResident) return;
    const channels = [];
    if (cntForm.sms) channels.push('SMS');
    if (cntForm.voice) channels.push('VOICE_CALL');
    if (channels.length === 0) {
      setError('Select at least one notification channel (SMS or VOICE_CALL).');
      return;
    }
    try {
      await apiFetch('/api/v1/emergency/contacts', {
        method: 'POST',
        body: JSON.stringify({
          resident_id: selectedResident.resident_id,
          full_name: cntForm.full_name,
          phone_number: cntForm.phone_number,
          relationship: cntForm.relationship,
          priority: Number(cntForm.priority),
          preferred_channels: channels,
          consent_status: cntForm.consent_status,
        }),
      });
      setCntForm({
        full_name: '',
        phone_number: '+91',
        relationship: '',
        priority: contacts.length + 2,
        sms: true,
        voice: true,
        consent_status: 'GRANTED',
      });
      await loadContacts(selectedResident.resident_id);
      setError('');
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDeactivateContact = async (contactId) => {
    try {
      await apiFetch(`/api/v1/emergency/contacts/${encodeURIComponent(contactId)}/deactivate`, {
        method: 'POST',
      });
      if (selectedResident) await loadContacts(selectedResident.resident_id);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
          <Users className="w-5 h-5 text-cyan-400" />
          Residents & Emergency Contacts
        </h2>
        <p className="text-xs text-slate-400">
          Register elderly residents, associate UNO Q nodes, and configure priority-ordered E.164 caregiver contacts
        </p>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-200 text-xs">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Resident List + Registration */}
        <div className="space-y-4">
          <form
            onSubmit={handleCreateResident}
            className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-3"
          >
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <UserPlus className="w-4 h-4 text-cyan-400" /> Register Resident
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <input
                required
                placeholder="Full Name"
                value={resForm.full_name}
                onChange={(e) => setResForm({ ...resForm, full_name: e.target.value })}
                className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100"
              />
              <input
                type="number"
                min="0"
                max="130"
                placeholder="Age (optional)"
                value={resForm.age}
                onChange={(e) => setResForm({ ...resForm, age: e.target.value })}
                className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100"
              />
              <input
                required
                placeholder="Residence Address / Location"
                value={resForm.address_location}
                onChange={(e) => setResForm({ ...resForm, address_location: e.target.value })}
                className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 sm:col-span-2"
              />
              <select
                value={resForm.associated_node_id}
                onChange={(e) => setResForm({ ...resForm, associated_node_id: e.target.value })}
                className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100"
              >
                <option value="">Associate UNO Q Node (optional)</option>
                {nodes.map((n) => (
                  <option key={n.node_id} value={n.node_id}>
                    {n.node_id} — {n.location}
                  </option>
                ))}
              </select>
              <select
                value={resForm.consent_status}
                onChange={(e) => setResForm({ ...resForm, consent_status: e.target.value })}
                className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100"
              >
                <option value="GRANTED">Consent: GRANTED</option>
                <option value="PENDING">Consent: PENDING</option>
                <option value="REVOKED">Consent: REVOKED</option>
              </select>
              <input
                placeholder="Restricted Safety Notes (optional)"
                value={resForm.safety_information}
                onChange={(e) => setResForm({ ...resForm, safety_information: e.target.value })}
                className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 sm:col-span-2"
              />
            </div>
            <button
              type="submit"
              className="px-4 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs transition"
            >
              Register Resident
            </button>
          </form>

          <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-2">
            <h3 className="text-sm font-bold text-slate-100 mb-2">
              Registered Residents ({residents.length})
            </h3>
            {residents.length === 0 ? (
              <p className="text-xs text-slate-400">No residents registered yet.</p>
            ) : (
              residents.map((r) => (
                <div
                  key={r.resident_id}
                  onClick={() => setSelectedResident(r)}
                  className={`p-3 rounded-lg border cursor-pointer transition flex items-center justify-between ${
                    selectedResident?.resident_id === r.resident_id
                      ? 'bg-cyan-500/10 border-cyan-500/40'
                      : 'bg-slate-950/50 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="text-xs">
                    <div className="font-bold text-slate-100">
                      {r.full_name}{' '}
                      <span className="font-mono text-[11px] text-slate-400">({r.resident_id})</span>
                    </div>
                    <div className="text-slate-400">
                      {r.address_location} • Node: {r.associated_node_id || 'Unassigned'} • Consent:{' '}
                      {r.consent_status}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                        r.active_status
                          ? 'bg-emerald-500/15 text-emerald-300'
                          : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {r.active_status ? 'ACTIVE' : 'INACTIVE'}
                    </span>
                    {r.active_status && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeactivateResident(r.resident_id);
                        }}
                        className="p-1 text-rose-400 hover:text-rose-300"
                        title="Deactivate Resident"
                      >
                        <UserX className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Selected Resident Details & Caregiver Contacts */}
        <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-4">
          {!selectedResident ? (
            <p className="text-xs text-slate-400 py-12 text-center">
              Select a resident on the left to manage emergency contacts and view restricted safety notes.
            </p>
          ) : (
            <>
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div>
                  <h3 className="text-sm font-bold text-slate-100">
                    Caregivers for {selectedResident.full_name}
                  </h3>
                  <p className="text-xs text-slate-400">
                    Ordered by priority (Level 1 = Primary, Level 2 = Secondary, Level 3 = Tertiary)
                  </p>
                </div>
                {selectedResident.has_safety_information && (
                  <button
                    type="button"
                    onClick={() => handleViewSafetyInfo(selectedResident.resident_id)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-amber-500/15 border border-amber-500/30 text-amber-300 text-[11px]"
                  >
                    {safetyAuthorized ? <Unlock className="w-3.5 h-3.5" /> : <Lock className="w-3.5 h-3.5" />}
                    {safetyAuthorized ? 'Safety Info Unlocked' : 'Unlock Safety Info'}
                  </button>
                )}
              </div>

              {safetyAuthorized && (
                <div className="p-3 rounded-lg bg-amber-950/40 border border-amber-700/50 text-xs text-amber-100">
                  <span className="font-bold flex items-center gap-1 mb-1">
                    <Shield className="w-3.5 h-3.5" /> Restricted Safety Information:
                  </span>
                  {safetyNote}
                </div>
              )}

              <div className="space-y-2">
                {contacts.map((c, idx) => (
                  <div
                    key={c.contact_id}
                    className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800 flex items-center justify-between text-xs"
                  >
                    <div>
                      <div className="font-semibold text-slate-100">
                        Level {Math.min(idx + 1, 3)} (P{c.priority}) — {c.full_name} ({c.relationship})
                      </div>
                      <div className="text-slate-400 font-mono text-[11px]">
                        {c.phone_number} • {c.preferred_channels.join(', ')} • Consent: {c.consent_status}
                      </div>
                    </div>
                    {c.active_status ? (
                      <button
                        onClick={() => handleDeactivateContact(c.contact_id)}
                        className="text-rose-400 hover:text-rose-300 text-[11px]"
                      >
                        Deactivate
                      </button>
                    ) : (
                      <span className="text-slate-500 text-[11px]">INACTIVE</span>
                    )}
                  </div>
                ))}
              </div>

              <form onSubmit={handleCreateContact} className="pt-3 border-t border-slate-800 space-y-2.5 text-xs">
                <h4 className="font-bold text-slate-200 flex items-center gap-1.5">
                  <Phone className="w-3.5 h-3.5 text-emerald-400" /> Add Emergency Contact (E.164)
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  <input
                    required
                    placeholder="Contact Full Name"
                    value={cntForm.full_name}
                    onChange={(e) => setCntForm({ ...cntForm, full_name: e.target.value })}
                    className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100"
                  />
                  <input
                    required
                    placeholder="+919876543210"
                    value={cntForm.phone_number}
                    onChange={(e) => setCntForm({ ...cntForm, phone_number: e.target.value })}
                    className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 font-mono"
                  />
                  <input
                    required
                    placeholder="Relationship (e.g. Son, Daughter)"
                    value={cntForm.relationship}
                    onChange={(e) => setCntForm({ ...cntForm, relationship: e.target.value })}
                    className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100"
                  />
                  <input
                    type="number"
                    min="1"
                    max="100"
                    value={cntForm.priority}
                    onChange={(e) => setCntForm({ ...cntForm, priority: e.target.value })}
                    className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100"
                    placeholder="Priority (1 = Primary)"
                  />
                </div>
                <div className="flex items-center gap-4 text-slate-300">
                  <label className="inline-flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={cntForm.sms}
                      onChange={(e) => setCntForm({ ...cntForm, sms: e.target.checked })}
                    />
                    SMS
                  </label>
                  <label className="inline-flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={cntForm.voice}
                      onChange={(e) => setCntForm({ ...cntForm, voice: e.target.checked })}
                    />
                    Voice Call
                  </label>
                </div>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold transition"
                >
                  Add Contact
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

