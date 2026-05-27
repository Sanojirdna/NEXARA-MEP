
export async function apiGet(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`GET ${path} failed`);
  }
  return response.json();
}

export async function apiPost(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`POST ${path} failed`);
  }
  return response.json();
}

export async function uploadAndBuild(ifcFile, excelFile, workers, configFile = null) {
  const formData = new FormData();
  formData.append("ifc_file", ifcFile);
  formData.append("excel_file", excelFile);
  formData.append("workers", String(workers));
  if (configFile) {
    formData.append("config_file", configFile);
  }

  const response = await fetch("/api/session/build", {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Build failed");
  }
  return response.json();
}

export async function importConfig(configFile) {
  const formData = new FormData();
  formData.append("config_file", configFile);

  const response = await fetch("/api/config/import", {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Config import failed");
  }
  return response.json();
}

export async function importProjectBundle(bundleFile, ifcFile = null) {
  const formData = new FormData();
  formData.append("bundle_file", bundleFile);
  if (ifcFile) {
    formData.append("ifc_file", ifcFile);
  }

  const response = await fetch("/api/session/import", {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Project bundle import failed");
  }
  return response.json();
}

export async function resetSession() {
  const response = await fetch("/api/session/reset", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Reset failed");
  }
  return response.json();
}
