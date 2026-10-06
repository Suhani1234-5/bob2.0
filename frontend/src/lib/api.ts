const API_BASE = "http://localhost:8000"

export async function getPR(prId: string) {
  const res = await fetch(`${API_BASE}/api/pr/${prId}`)
  return res.json()
}

export async function getFindings(prId: string) {
  const res = await fetch(`${API_BASE}/api/pr/${prId}/findings`)
  return res.json()
}

export async function getFindingDetail(findingId: string) {
  const res = await fetch(`${API_BASE}/api/findings/${findingId}`)
  return res.json()
}

export async function getFindingTests(findingId: string) {
  const res = await fetch(`${API_BASE}/api/findings/${findingId}/tests`)
  return res.json()
}

export async function getFindingPatch(findingId: string) {
  const res = await fetch(`${API_BASE}/api/findings/${findingId}/patch`)
  return res.json()
}

export async function getFindingEvidence(findingId: string) {
  const res = await fetch(`${API_BASE}/api/findings/${findingId}/evidence`);
  return res.json();
}