const pageType = document.body.dataset.page;
const API = "";

const toast = document.getElementById("toast");

function showToast(message) {
	if (!toast) {
		return;
	}
	toast.textContent = message;
	toast.classList.add("show");
	setTimeout(() => toast.classList.remove("show"), 2200);
}

function getToken() {
	return localStorage.getItem("dontgrade_token");
}

function setToken(token) {
	localStorage.setItem("dontgrade_token", token);
}

function clearSession() {
	localStorage.removeItem("dontgrade_token");
	localStorage.removeItem("dontgrade_email");
}

function setUserEmail(email) {
	localStorage.setItem("dontgrade_email", email);
	const currentUserEmail = document.getElementById("currentUserEmail");
	if (currentUserEmail) {
		currentUserEmail.textContent = email;
	}
}

function parseSuggestions(raw) {
	const output = {
		abbreviationStatus: "abbrevation may not exist or rarely used",
		abbreviationPairs: [],
		formalContext: "",
		informalContext: "",
		rewrites: [],
	};

	if (!raw) {
		return output;
	}

	const lines = raw
		.split("\n")
		.map((line) => line.replace(/^[-*•\s]+/, "").trim())
		.filter(Boolean);

	for (const line of lines) {
		if (line.startsWith("Abbreviation status:")) {
			output.abbreviationStatus = line;
			const pairsText = line.replace("Abbreviation status:", "").trim();
			const pairs = pairsText
				.split("|")
				.map((item) => item.trim())
				.filter(Boolean);

			output.abbreviationPairs = pairs
				.map((pair) => {
					const [short, ...rest] = pair.split("->");
					if (!short || !rest.length) {
						return null;
					}
					return {
						short: short.trim(),
						full: rest.join("->").trim(),
					};
				})
				.filter(Boolean);
			continue;
		}

		if (line === "abbrevation may not exist or rarely used") {
			output.abbreviationStatus = line;
			continue;
		}

		if (line.startsWith("Formal sentence way:")) {
			output.formalContext = line;
			continue;
		}

		if (line.startsWith("Informal sentence way:")) {
			output.informalContext = line;
			continue;
		}

		if (line.startsWith("Rewrite")) {
			output.rewrites.push(line);
		}
	}

	return output;
}

function readabilityLabel(score) {
	if (score >= 60) {
		return "Easy";
	}
	if (score >= 30) {
		return "Medium";
	}
	return "Hard";
}

async function fetchJson(path, options = {}) {
	const response = await fetch(`${API}${path}`, options);
	const text = await response.text();

	let data = null;
	try {
		data = text ? JSON.parse(text) : null;
	} catch (_error) {
		data = null;
	}

	if (!response.ok) {
		const detail = data && data.detail ? data.detail : `Request failed: ${response.status}`;
		throw new Error(detail);
	}

	return data;
}

function initSignupPage() {
	const signupForm = document.getElementById("signupForm");
	if (!signupForm) {
		return;
	}

	signupForm.addEventListener("submit", async (event) => {
		event.preventDefault();

		try {
			await fetchJson("/signup", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					username: document.getElementById("signupUsername").value,
					email: document.getElementById("signupEmail").value,
					password: document.getElementById("signupPassword").value,
				}),
			});
			showToast("Signup successful. Redirecting to login...");
			signupForm.reset();
			setTimeout(() => {
				window.location.href = "/login";
			}, 800);
		} catch (error) {
			showToast(error.message);
		}
	});
}

function initLoginPage() {
	const loginForm = document.getElementById("loginForm");
	if (!loginForm) {
		return;
	}

	loginForm.addEventListener("submit", async (event) => {
		event.preventDefault();

		try {
			const email = document.getElementById("loginEmail").value;
			const password = document.getElementById("loginPassword").value;
			const body = new URLSearchParams({ username: email, password });

			const data = await fetchJson("/login", {
				method: "POST",
				headers: { "Content-Type": "application/x-www-form-urlencoded" },
				body,
			});

			setToken(data.access_token);
			setUserEmail(email);
			showToast("Logged in");
			loginForm.reset();
			setTimeout(() => {
				window.location.href = "/";
			}, 350);
		} catch (error) {
			showToast(error.message);
		}
	});
}

function renderAnalysis(data) {
	const gradeLevel = document.getElementById("gradeLevel");
	const readabilityClass = document.getElementById("readabilityClass");
	const resultAbbreviation = document.getElementById("resultAbbreviation");
	const suggestionList = document.getElementById("suggestionList");

	gradeLevel.textContent = `Grade ${Math.round(data.grade_level)}`;
	readabilityClass.textContent = readabilityLabel(data.reading_ease);

	suggestionList.innerHTML = "";
	resultAbbreviation.innerHTML = "";
	const suggestions = parseSuggestions(data.clear_text);

	const abbrCard = document.createElement("div");
	abbrCard.className = "suggestion-section";
	const abbrTitle = document.createElement("h4");
	abbrTitle.textContent = "Abbreviation";
	abbrCard.appendChild(abbrTitle);

	if (suggestions.abbreviationPairs.length) {
		const pairList = document.createElement("div");
		pairList.className = "abbr-pair-list";

		suggestions.abbreviationPairs.forEach((pair) => {
			const pairRow = document.createElement("div");
			pairRow.className = "abbr-pair-row";
			pairRow.innerHTML = `
				<span class="abbr-short">${pair.short}</span>
				<span class="abbr-arrow">-></span>
				<span class="abbr-full">${pair.full}</span>
			`;

			const copyBtn = document.createElement("button");
			copyBtn.className = "copy-btn";
			copyBtn.textContent = "Copy";
			copyBtn.addEventListener("click", async () => {
				try {
					await navigator.clipboard.writeText(pair.full);
					showToast("Copied full abbreviation");
				} catch (_error) {
					showToast("Copy failed on this browser");
				}
			});

			pairRow.appendChild(copyBtn);
			pairList.appendChild(pairRow);
		});

		abbrCard.appendChild(pairList);
	} else {
		const noAbbr = document.createElement("p");
		noAbbr.textContent = suggestions.abbreviationStatus;
		abbrCard.appendChild(noAbbr);
	}

	const contextCard = document.createElement("div");
	contextCard.className = "suggestion-section";
	contextCard.innerHTML = `
		<h4>Context</h4>
		<p>${suggestions.formalContext || "Formal context is not available."}</p>
		<p>${suggestions.informalContext || "Informal context is not available."}</p>
	`;

	const rewriteCard = document.createElement("div");
	rewriteCard.className = "suggestion-section";
	rewriteCard.innerHTML = "<h4>Rewrite Suggestions</h4>";
	if (suggestions.rewrites.length) {
		const rewriteList = document.createElement("ul");
		rewriteList.className = "rewrite-list";
		suggestions.rewrites.forEach((rewrite) => {
			const li = document.createElement("li");
			li.textContent = rewrite;
			rewriteList.appendChild(li);
		});
		rewriteCard.appendChild(rewriteList);
	} else {
		const empty = document.createElement("p");
		empty.textContent = "No rewrites available.";
		rewriteCard.appendChild(empty);
	}

	resultAbbreviation.appendChild(abbrCard);
	suggestionList.appendChild(contextCard);
	suggestionList.appendChild(rewriteCard);
}

function renderHistory(items) {
	const historyList = document.getElementById("historyList");
	if (!historyList) {
		return;
	}

	historyList.innerHTML = "";

	if (!items.length) {
		historyList.innerHTML = "<p>No history yet. Analyze a text first.</p>";
		return;
	}

	items.forEach((entry) => {
		const div = document.createElement("div");
		div.className = "history-item";
		div.innerHTML = `
			<p><strong>Text:</strong> ${entry.input_text}</p>
			<p><strong>Grade:</strong> ${entry.grade_level.toFixed(1)} | ${readabilityLabel(entry.reading_ease)}</p>
			<p><strong>Date:</strong> ${new Date(entry.created_at).toLocaleString()}</p>
		`;
		historyList.appendChild(div);
	});
}

async function initMainPage() {
	const token = getToken();
	if (!token) {
		window.location.href = "/login";
		return;
	}

	const inputText = document.getElementById("inputText");
	const analyzeBtn = document.getElementById("analyzeBtn");
	const clearBtn = document.getElementById("clearBtn");
	const logoutBtn = document.getElementById("logoutBtn");

	try {
		const me = await fetchJson("/me", {
			headers: { Authorization: `Bearer ${token}` },
		});
		setUserEmail(me.email);
	} catch (_error) {
		clearSession();
		window.location.href = "/login";
		return;
	}

	analyzeBtn.addEventListener("click", async () => {
		const text = inputText.value.trim();
		if (!text) {
			showToast("Enter text to analyze.");
			return;
		}

		analyzeBtn.disabled = true;
		analyzeBtn.textContent = "Analyzing...";

		try {
			const data = await fetchJson("/analyze", {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					Authorization: `Bearer ${token}`,
				},
				body: JSON.stringify({ input_text: text }),
			});

			renderAnalysis(data);
			showToast("Analysis complete.");
		} catch (error) {
			showToast(error.message);
		} finally {
			analyzeBtn.disabled = false;
			analyzeBtn.textContent = "Analyze Text";
		}
	});

	clearBtn.addEventListener("click", () => {
		inputText.value = "";
		document.getElementById("suggestionList").innerHTML = "";
		document.getElementById("resultAbbreviation").innerHTML = "";
		document.getElementById("gradeLevel").textContent = "-";
		document.getElementById("readabilityClass").textContent = "-";
	});

	logoutBtn.addEventListener("click", () => {
		clearSession();
		window.location.href = "/login";
	});
}

async function initHistoryPage() {
	const token = getToken();
	if (!token) {
		window.location.href = "/login";
		return;
	}

	const logoutBtn = document.getElementById("logoutBtn");
	const refreshHistoryBtn = document.getElementById("refreshHistoryBtn");

	async function loadHistory() {
		const history = await fetchJson("/history", {
			headers: { Authorization: `Bearer ${token}` },
		});
		renderHistory(history);
	}

	try {
		const me = await fetchJson("/me", {
			headers: { Authorization: `Bearer ${token}` },
		});
		setUserEmail(me.email);
		await loadHistory();
	} catch (_error) {
		clearSession();
		window.location.href = "/login";
		return;
	}

	refreshHistoryBtn.addEventListener("click", async () => {
		try {
			await loadHistory();
			showToast("History refreshed");
		} catch (error) {
			showToast(error.message);
		}
	});

	logoutBtn.addEventListener("click", () => {
		clearSession();
		window.location.href = "/login";
	});
}

if (pageType === "signup") {
	initSignupPage();
} else if (pageType === "login") {
	initLoginPage();
} else if (pageType === "history") {
	initHistoryPage();
} else {
	initMainPage();
}
