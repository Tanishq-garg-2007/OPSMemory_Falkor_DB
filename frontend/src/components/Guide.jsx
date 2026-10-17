import { useEffect } from "react";

const resolveImg = (name) => {
  const base = import.meta.env.BASE_URL || "/ui/";
  return `${base.endsWith("/") ? base : base + "/"}images/${name}`;
};

export default function Guide({ onClose }) {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="guide-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="presentation"
    >
      <div className="guide-modal" role="dialog" aria-modal="true" aria-label="OpsMemory Frontend Guide">
        <div className="guide-head">
          <div className="guide-head-left">
            <span className="logo-badge">
              <img src={resolveImg("../favicon-96x96.png")} alt="" className="logo-icon" />
              <span>OpsMemory</span>
            </span>
            <span className="badge">Guide</span>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={onClose} aria-label="Close Guide" data-tooltip="Close Walkthrough: Return to the active OpsMemory console." data-tooltip-pos="left">
            Close
          </button>
        </div>

        <div className="guide-body">
          {/* 1. Title */}
          <header className="guide-title-block">
            <h1 className="guide-main-title">OpsMemory: Frontend Guide</h1>
            <p className="guide-subtitle"> Topic: Agent Memory and Coordination</p>
            <div className="guide-team-banner">
              <span>Tanishq Garg</span>
              <span className="guide-dot">•</span>
              <span>Gautam Jain</span>
              <span className="guide-dot">•</span>
              <span>Disha Gupta</span>
            </div>
          </header>

          {/* 2. What is OpsMemory? */}
          <section className="guide-section">
            <h2>What is OpsMemory?</h2>
            <p>
              OpsMemory is a persistent memory workspace for engineering and support teams.
              Imagine a team resolves a critical website failure in the middle of the night.
              Weeks later, a similar issue appears, but the on-call engineer has changed and nobody recalls the solution.
              OpsMemory preserves that operational experience across sessions so the answer remains instantly available.
              Every generated answer is produced by a real language model and shows the exact stored memories used to ground it.
            </p>
          </section>

          {/* 3. Start here in 3 minutes */}
          <section className="guide-section">
            <h2>Start here in 3 minutes</h2>
            <p>Follow these three quick steps to see OpsMemory in action:</p>
            <ol className="guide-steps-list">
              <li>
                <strong>Open the app in the browser.</strong> You will see the main workspace with the chat on the left and evidence on the right.
              </li>
              <li>
                <strong>Open Admin and choose Seed Fixtures.</strong> The page prompts for the admin key (Default key: <code>test_admin_secret</code>, defined in <code>.env</code>). This loads sample services, incidents, and runbooks.
              </li>
              <li>
                <strong>Ask &quot;What happened in inc-101?&quot;</strong> Type this into the chat box at the bottom and press Send to see a grounded response with citations.
              </li>
            </ol>
            <figure className="guide-figure">
              <p className="guide-figure-desc">The start screen displays a clean workspace ready for your first operational inquiry.</p>
              <img
                src={resolveImg("01-start-page.png")}
                alt="OpsMemory start screen"
                className="guide-screenshot"
                onError={(e) => { e.currentTarget.style.display = "none"; }}
              />
              <figcaption className="guide-caption">OpsMemory start screen overview</figcaption>
            </figure>
          </section>

          {/* 4. The screen at a glance */}
          <section className="guide-section">
            <h2>The screen at a glance</h2>
            <div className="guide-diagram-box">
              <pre className="guide-diagram">{`+-----------------------------------------------------------------------------------+
|  HEADER: [Logo v0.1.0] [Tenant: Acme Corp] [Memory Graph] [Board 1] [Admin] [Guide] [Mode] |
+-----------------------------------------------------------------------------------+
|  TITLE: AGENT MEMORY AND COORDINATION                                             |
+--------------------------------------------------+--------------------------------+
|  CONVERSATION & INCIDENT TRIAGE                  |  RETRIEVED EVIDENCE & CITATIONS|
|  (Wide left panel)                               |  (Right panel)                 |
|                                                  |                                |
|  - System welcome banner                         |  - Evidence count badge        |
|  - Questions (sand notes)                        |  - Memory cards with scores    |
|  - Answers (paper clippings with terracotta edge)|  - Active / superseded flags   |
|  - Reasoning paths and learned items             |  - Show in graph button        |
|  - Chat input bar with Send button               |                                |
+--------------------------------------------------+--------------------------------+
|  BOARD DRAWER (Slides out from the right over the main panels):                   |
|  [Task Board]  [Agents]  [Timeline]  [Memory Inspector]                           |
+-----------------------------------------------------------------------------------+`}</pre>
            </div>

            <table className="guide-table">
              <thead>
                <tr>
                  <th style={{ width: "30%" }}>Area</th>
                  <th>What it is for</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>Header</strong></td>
                  <td>Contains tenant selection, primary views (Memory Graph, Board, Guide), administrative tools, connection status, and theme controls.</td>
                </tr>
                <tr>
                  <td><strong>Title</strong></td>
                  <td>Displays the hackathon project banner emphasizing agent memory and coordination.</td>
                </tr>
                <tr>
                  <td><strong>Conversation area</strong></td>
                  <td>The wide left section where you ask questions, review past sessions, and read grounded answers with citations.</td>
                </tr>
                <tr>
                  <td><strong>Retrieved Evidence area</strong></td>
                  <td>The right section displaying individual stored memory cards retrieved to verify and answer your question.</td>
                </tr>
                <tr>
                  <td><strong>Board drawer</strong></td>
                  <td>A slide-out panel containing coordination tasks, multi-agent handoffs, entity timelines, and raw inspection data.</td>
                </tr>
              </tbody>
            </table>
          </section>

          {/* 5. Feature guide */}
          <section className="guide-section">
            <h2>Feature guide</h2>

            {/* 5a. The header */}
            <div className="guide-feature-block">
              <h3>a. The header</h3>
              <p><strong>What it is:</strong> The persistent top navigation bar visible across all screens.</p>
              <p>
                <strong>What you see:</strong> The OpsMemory logo, version tag (v0.1.0), Tenant selector,
                Memory Graph button, Board button with open task count badge, Admin menu dropdown,
                connection status badge, light and dark theme toggle, and the Guide button.
              </p>
              <p>
                <strong>What you can do:</strong> Switch organizations, launch visual graphs, open the coordination drawer,
                seed or reset data, inspect connection health, switch themes, and open this walkthrough.
              </p>
              <p className="guide-why">
                <em>Why it matters:</em> Keeps key workflow controls and system health immediately accessible at all times.
              </p>
            </div>

            {/* 5b. Tenants */}
            <div className="guide-feature-block">
              <h3>b. Tenants</h3>
              <p><strong>What it is:</strong> Organizational boundaries dividing separate operational domains.</p>
              <p>
                <strong>What you see:</strong> A dropdown menu showing &quot;Acme Corp (acme)&quot; and &quot;Beta Labs (beta)&quot;.
              </p>
              <p>
                <strong>What you can do:</strong> Click the dropdown to switch tenants at any moment.
              </p>
              <p className="guide-why">
                <em>Why it matters:</em> Guarantees strict isolation so Acme Corp and Beta Labs each maintain distinct memories with zero cross-visibility.
              </p>
            </div>

            {/* 5c. Asking questions */}
            <div className="guide-feature-block">
              <h3>c. Asking questions</h3>
              <p><strong>What it is:</strong> The natural language conversation and incident triage interface.</p>
              <p>
                <strong>What you see:</strong> Your prompt rendered as a sand-coloured note on the right; the answer rendered as a textured paper clipping
                with a terracotta left accent bar on the left; animated pulsing dots indicating active memory retrieval; citations listing memory identifiers;
                and reasoning path chips showing service dependency chains. When new operational facts are detected, a &quot;Learned this turn&quot; box highlights
                created memories, superseded items, and newly created tasks. At the top of the panel, you will find the &quot;+ New&quot; conversation button,
                the &quot;History&quot; button to browse past sessions, and the conversation session badge.
              </p>
              <p>
                <strong>What you can do:</strong> Enter operational queries, report new outages, start clean conversations with &quot;+ New&quot;,
                or reopen prior discussions with &quot;History&quot;.
              </p>
              <p className="guide-why">
                <em>Why it matters:</em> Enables engineers to query historical knowledge and document updates naturally, backed by clear evidence.
              </p>
              <figure className="guide-figure">
                <p className="guide-figure-desc">A completed chat response displays reasoning paths, citations, and learned items.</p>
                <img
                  src={resolveImg("02-chat-answer.png")}
                  alt="Chat answer with citations and reasoning paths"
                  className="guide-screenshot"
                  onError={(e) => { e.currentTarget.style.display = "none"; }}
                />
                <figcaption className="guide-caption">Grounded answer with citations and reasoning paths</figcaption>
              </figure>
            </div>

            {/* 5d. Evidence cards */}
            <div className="guide-feature-block">
              <h3>d. Evidence cards</h3>
              <p><strong>What it is:</strong> Individual cards showing stored knowledge records retrieved to construct the answer.</p>
              <p>
                <strong>What you see:</strong> Each card displays the memory title, detailed summary, unique memory ID,
                Conf (confidence percentage indicating certainty), Score (relevance match metric),
                Valid (effective time interval), and Status. Active records feature green accents; superseded records feature struck-through titles,
                muted text, and a folded corner ribbon; conflicted records display warning badges.
              </p>
              <p>
                <strong>What you can do:</strong> Click any card to inspect its full details in the Board drawer, or click &quot;Show in graph&quot;.
              </p>
              <p className="guide-why">
                <em>Why it matters:</em> Delivers complete transparency so operators can verify why the model provided a specific recommendation.
              </p>
              <figure className="guide-figure">
                <p className="guide-figure-desc">Retrieved evidence cards present scores, confidence levels, and active validity periods.</p>
                <img
                  src={resolveImg("03-evidence-cards.png")}
                  alt="Retrieved evidence cards"
                  className="guide-screenshot"
                  onError={(e) => { e.currentTarget.style.display = "none"; }}
                />
                <figcaption className="guide-caption">Retrieved evidence cards with match score and validity</figcaption>
              </figure>
            </div>

            {/* 5e. Show in graph */}
            <div className="guide-feature-block">
              <h3>e. Show in graph</h3>
              <p><strong>What it is:</strong> A direct visual navigation action placed on each evidence card.</p>
              <p>
                <strong>What you see:</strong> A button labelled &quot;Show in graph&quot; located at the lower edge of every evidence card.
              </p>
              <p>
                <strong>What you can do:</strong> Click the button to immediately open the Memory Graph modal with that specific memory node selected and centered.
              </p>
              <p className="guide-why">
                <em>Why it matters:</em> Bridges reading textual evidence with exploring structural relationships in the interactive graph.
              </p>
              <figure className="guide-figure">
                <p className="guide-figure-desc">Clicking Show in graph on an evidence card immediately focuses the memory node in the interactive graph.</p>
                <img
                  src={resolveImg("04-show-in-graph.png")}
                  alt="Show in graph action"
                  className="guide-screenshot"
                  onError={(e) => { e.currentTarget.style.display = "none"; }}
                />
                <figcaption className="guide-caption">Focusing memory node in the interactive graph</figcaption>
              </figure>
            </div>

            {/* 5f. The Board drawer */}
            <div className="guide-feature-block">
              <h3>f. The Board drawer</h3>
              <p><strong>What it is:</strong> A sliding side drawer opened by clicking the &quot;Board&quot; button in the header.</p>
              <p>
                <strong>What you see:</strong> A four-tab navigation interface containing Task Board, Agents, Timeline, and Memory Inspector.
              </p>
              <ul className="guide-bullet-list">
                <li>
                  <strong>Task Board:</strong> Displays operational coordination cards laid out across an open-book design with a center spine.
                  Cards display task type, status badge (pending, claimed, done, resolved), task ID, lease owner, and a &quot;Refresh Tasks&quot; button.
                </li>
                <li>
                  <strong>Agents:</strong> Illustrates the multi-agent relay for the latest question. Displays three agents in sequential order:
                  Step 1 (Triage) &rarr; Step 2 (Resolver) &rarr; Step 3 (Curator), each with their assigned task ID and connected by directional arrows.
                  If no handoff occurred, it displays &quot;No handoffs recorded for this turn.&quot; while remaining accessible.
                </li>
                <li>
                  <strong>Timeline:</strong> Features an Entity dropdown menu (such as payments-api) populated from graph entities.
                  Renders memories in date order on alternating book pages. Outdated entries are struck through with arrows pointing directly
                  to their replacement (↳ Superseded by). Shows &quot;No memories about this entity yet.&quot; when empty.
                </li>
                <li>
                  <strong>Memory Inspector:</strong> Provides a raw structured view of tenant records with &quot;Load All Memories&quot; and &quot;Open Graph View&quot; buttons.
                </li>
              </ul>
              <p>
                <strong>What you can do:</strong> Track active tasks, audit agent coordination, explore component history over time, and inspect raw records.
              </p>
              <p className="guide-why">
                <em>Why it matters:</em> Brings multi-agent coordination and historical knowledge evolution into plain view.
              </p>
              <figure className="guide-figure">
                <p className="guide-figure-desc">The Agents tab reveals the Triage to Resolver to Curator coordination chain.</p>
                <img
                  src={resolveImg("05-board-agents.png")}
                  alt="Agents coordination relay in Board drawer"
                  className="guide-screenshot"
                  onError={(e) => { e.currentTarget.style.display = "none"; }}
                />
                <figcaption className="guide-caption">Multi-agent coordination relay (Triage → Resolver → Curator)</figcaption>
              </figure>
              <figure className="guide-figure">
                <p className="guide-figure-desc">The Timeline tab illustrates superseded facts pointing forward to current production versions.</p>
                <img
                  src={resolveImg("06-board-timeline.png")}
                  alt="Entity memory timeline in Board drawer"
                  className="guide-screenshot"
                  onError={(e) => { e.currentTarget.style.display = "none"; }}
                />
                <figcaption className="guide-caption">Entity memory timeline showing historical supersession</figcaption>
              </figure>
            </div>

            {/* 5g. Memory Graph */}
            <div className="guide-feature-block">
              <h3>g. Memory Graph</h3>
              <p><strong>What it is:</strong> A full-screen interactive topology visualization of operational knowledge.</p>
              <p>
                <strong>What you see:</strong> Nodes represented as circles and relationships represented as lines with arrows.
                Solid lines indicate dependencies, while dashed red lines signify replacement (supersedes) relationships.
              </p>

              <table className="guide-table">
                <thead>
                  <tr>
                    <th>Node Type</th>
                    <th>Color</th>
                    <th>Meaning</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>Entity</strong></td>
                    <td>Forest Green</td>
                    <td>Technical components, teams, users, or services (e.g. payments-api, postgres-orders).</td>
                  </tr>
                  <tr>
                    <td><strong>Memory</strong></td>
                    <td>Terracotta Orange</td>
                    <td>Recorded facts, runbooks, escalation procedures, and incident memories.</td>
                  </tr>
                  <tr>
                    <td><strong>Source</strong></td>
                    <td>Warm Gold</td>
                    <td>Origin documents, tickets, or inputs that gave rise to memories.</td>
                  </tr>
                  <tr>
                    <td><strong>Agent</strong></td>
                    <td>Plum Purple</td>
                    <td>Autonomous agents responsible for triage, resolution, and memory curation.</td>
                  </tr>
                  <tr>
                    <td><strong>Task</strong></td>
                    <td>Sage Green</td>
                    <td>Coordination tasks tracked and claimed on the board.</td>
                  </tr>
                  <tr>
                    <td><strong>Conversation</strong></td>
                    <td>Slate Blue</td>
                    <td>Top-level conversational sessions (starts hidden in legend to preserve clarity).</td>
                  </tr>
                  <tr>
                    <td><strong>Session</strong></td>
                    <td>Khaki Taupe</td>
                    <td>Session containers (starts hidden in legend to preserve clarity).</td>
                  </tr>
                  <tr>
                    <td><strong>Turn</strong></td>
                    <td>Sand Wheat</td>
                    <td>Individual user and assistant messages (starts hidden in legend to preserve clarity).</td>
                  </tr>
                </tbody>
              </table>

              <p>
                <strong>What you can do:</strong> Click any node to open its sidebar detail panel showing label, type, status, ID, and connected links.
                Click on the background to clear selection. Non-connected nodes automatically dim to highlight relationship paths.
                Toggle legend chips to show or hide node types. Click &quot;Show JSON&quot; to inspect raw structures, click &quot;Close&quot;, or press Escape to exit.
              </p>
              <p className="guide-why">
                <em>Why it matters:</em> Gives an intuitive structural overview of complex dependencies and service relationships.
              </p>
              <figure className="guide-figure">
                <p className="guide-figure-desc">The interactive graph highlights connected nodes and reveals relationship details.</p>
                <img
                  src={resolveImg("07-memory-graph.png")}
                  alt="Interactive Memory Graph"
                  className="guide-screenshot"
                  onError={(e) => { e.currentTarget.style.display = "none"; }}
                />
                <figcaption className="guide-caption">Interactive Memory Graph topology visualization</figcaption>
              </figure>
            </div>

            {/* 5h. Admin menu */}
            <div className="guide-feature-block">
              <h3>h. Admin menu &amp; Privilege Separation</h3>
              <p><strong>What it is:</strong> A dedicated administrative control panel providing secure fixture management and tenant data isolation.</p>
              <p>
                <strong>Why Privilege Separation Matters:</strong> Standard operators interact via <code>X-Tenant-Key</code> (e.g. <code>key_acme_secret</code>) which strictly scopes their access to incident chat and retrieval. Regular users cannot wipe databases or re-seed graph topologies. Destructive operations require the dedicated <code>X-Admin-Key</code>, protected by constant-time cryptographic verification (<code>hmac.compare_digest</code>).
              </p>
              <p>
                <strong>What you see:</strong> An &quot;Admin &#9662;&quot; button revealing &quot;Seed Fixtures&quot; and &quot;Reset Data&quot; (highlighted in red danger styling).
              </p>
              <p>
                <strong>What you can do &amp; Endpoint Roles:</strong>
              </p>
              <ul className="guide-list" style={{ marginTop: "0.5rem", marginBottom: "0.5rem" }}>
                <li><strong>Seed Fixtures (<code>POST /v1/admin/seed</code>):</strong> Instantly populates realistic incident postmortems, dependency graphs, runbooks, and preferences into FalkorDB for evaluation and demonstrations.</li>
                <li><strong>Reset Data (<code>POST /v1/admin/reset</code>):</strong> Completely purges all stored knowledge, tasks, and dialogue turns for the tenant back to a clean slate.</li>
              </ul>
              <p>
                When triggered, the browser requests the admin key (Default key: <code>test_admin_secret</code>, defined in <code>.env</code>). The key is stored temporarily in <code>sessionStorage</code> and disappears as soon as the browser tab closes.
              </p>
              <p className="guide-why">
                <em>Why it matters:</em> Guarantees high-privilege operations remain isolated from everyday chat users while allowing hackathon judges to reset and re-seed the environment in seconds.
              </p>
              <figure className="guide-figure">
                <p className="guide-figure-desc">The Admin dropdown provides fast fixture population and data reset capabilities.</p>
                <img
                  src={resolveImg("08-admin-menu.png")}
                  alt="Admin menu with seed and reset options"
                  className="guide-screenshot"
                  onError={(e) => { e.currentTarget.style.display = "none"; }}
                />
                <figcaption className="guide-caption">Admin menu with seed and reset options</figcaption>
              </figure>
            </div>

            {/* 5i. Light and dark themes */}
            <div className="guide-feature-block">
              <h3>i. Light and dark themes</h3>
              <p><strong>What it is:</strong> Aesthetic visual modes designed for readable operation.</p>
              <p>
                <strong>What you see:</strong> Light mode adopts a tactile parchment look with warm cream sheets, dark ink, and subtle grain.
                Dark mode adopts a night-time leather journal look with deep espresso surfaces and amber accents.
              </p>
              <p>
                <strong>What you can do:</strong> Click the sun/moon icon button in the header at any time to switch themes.
              </p>
              <p className="guide-why">
                <em>Why it matters:</em> Ensures high readability and reduced eye strain during extended incident reviews.
              </p>
              <figure className="guide-figure">
                <p className="guide-figure-desc">The dark theme provides a warm, low-contrast night journal aesthetic.</p>
                <img
                  src={resolveImg("09-dark-theme.png")}
                  alt="OpsMemory in dark theme"
                  className="guide-screenshot"
                  onError={(e) => { e.currentTarget.style.display = "none"; }}
                />
                <figcaption className="guide-caption">OpsMemory in warm dark theme</figcaption>
              </figure>
            </div>

            {/* 5j. The status badge */}
            <div className="guide-feature-block">
              <h3>j. The status badge</h3>
              <p><strong>What it is:</strong> A real-time connection status pill located in the header.</p>
              <p><strong>What you see:</strong> A status dot and label reflecting the current state:</p>
              <ul className="guide-bullet-list">
                <li><code>Checking...</code> &mdash; The application is verifying connection health.</li>
                <li><code>healthy</code> (or mode name with healthy) &mdash; The system is operational and connected.</li>
                <li><code>Degraded (Persistence Offline)</code> &mdash; The persistent store is unreachable.</li>
                <li><code>Offline</code> &mdash; The application cannot reach its communication channels.</li>
              </ul>
              <p>
                <strong>What you can do:</strong> Review the indicator to confirm readiness before issuing complex queries.
              </p>
              <p className="guide-why">
                <em>Why it matters:</em> Provides instant visual reassurance that operations are actively connected and healthy.
              </p>
            </div>
          </section>

          {/* 6. Judge's walkthrough */}
          <section className="guide-section">
            <h2>Judge&apos;s walkthrough (about 5 minutes)</h2>
            <p>Follow these numbered steps for a complete five-minute evaluation of the frontend:</p>

            <div className="guide-walkthrough-step">
              <h4>1. Seed the Acme Corp tenant</h4>
              <p>Select &quot;Acme Corp (acme)&quot; in the Tenant dropdown. Click Admin &rarr; Seed Fixtures. When prompted for the key, enter the admin key (Default key: <code>test_admin_secret</code>, defined in <code>.env</code>).</p>
              <p className="guide-expected"><strong>What you should see:</strong> An alert confirming memories, entities, and tasks were seeded successfully.</p>
            </div>

            <div className="guide-walkthrough-step">
              <h4>2. Ask about a past incident</h4>
              <p>In the chat input bar, type &quot;What happened in inc-101?&quot; and click Send.</p>
              <p className="guide-expected"><strong>What you should see:</strong> Pulsing typing dots, followed by a grounded answer detailing the checkout failure, with reasoning path chips and citation identifiers.</p>
            </div>

            <div className="guide-walkthrough-step">
              <h4>3. Examine retrieved evidence</h4>
              <p>Inspect the Retrieved Evidence panel on the right side of the screen.</p>
              <p className="guide-expected"><strong>What you should see:</strong> Detailed evidence cards displaying confidence percentages, match scores, and validity dates.</p>
            </div>

            <div className="guide-walkthrough-step">
              <h4>4. Navigate into the interactive graph</h4>
              <p>Click the &quot;Show in graph&quot; button on one of the evidence cards.</p>
              <p className="guide-expected"><strong>What you should see:</strong> The Memory Graph opens in a full modal with that specific memory node selected and its relationship connections illuminated.</p>
            </div>

            <div className="guide-walkthrough-step">
              <h4>5. Explore graph nodes and details</h4>
              <p>Click an Entity node (such as payments-api) and examine the detail sidebar.</p>
              <p className="guide-expected"><strong>What you should see:</strong> The sidebar lists connected relationships with directional indicators. Non-connected nodes dim. Press Escape or click Close to exit.</p>
            </div>

            <div className="guide-walkthrough-step">
              <h4>6. Inspect multi-agent coordination</h4>
              <p>Click the &quot;Board&quot; button in the header, then click the &quot;Agents&quot; tab in the drawer.</p>
              <p className="guide-expected"><strong>What you should see:</strong> A clear three-step relay showing Triage &rarr; Resolver &rarr; Curator, showing the task each agent claimed, joined by arrows.</p>
            </div>

            <div className="guide-walkthrough-step">
              <h4>7. Review the memory timeline for an entity</h4>
              <p>Click the &quot;Timeline&quot; tab in the Board drawer and verify &quot;payments-api&quot; is chosen in the Entity dropdown.</p>
              <p className="guide-expected"><strong>What you should see:</strong> Historical records arranged along the book spine in date order, with replaced facts struck through and pointing forward to newer versions.</p>
            </div>

            <div className="guide-walkthrough-step">
              <h4>8. Verify tenant isolation</h4>
              <p>Change the Tenant selector to &quot;Beta Labs (beta)&quot;.</p>
              <p className="guide-expected"><strong>What you should see:</strong> The chat and board reset immediately. Acme Corp records are completely invisible, verifying strict organizational separation.</p>
            </div>

            <div className="guide-walkthrough-step">
              <h4>9. Test the visual theme toggle</h4>
              <p>Click the theme toggle button in the header.</p>
              <p className="guide-expected"><strong>What you should see:</strong> The application smoothly transitions between parchment light mode and dark journal mode.</p>
            </div>

            <div className="guide-walkthrough-step">
              <h4>10. Open and dismiss the Guide</h4>
              <p>Click the &quot;Guide&quot; button in the header, review the text, then press the Escape key.</p>
              <p className="guide-expected"><strong>What you should see:</strong> The Guide opens smoothly over the workspace and closes cleanly upon pressing Escape.</p>
            </div>
          </section>

          {/* 7. Judge's checklist */}
          <section className="guide-section">
            <h2>Judge&apos;s checklist</h2>
            <p>Use these checkboxes to track your evaluation progress:</p>
            <ul className="guide-checklist">
              <li>[ ] Open the app and seed Acme Corp using Seed Fixtures in the Admin menu.</li>
              <li>[ ] Submit a question about inc-101 and observe the grounded response.</li>
              <li>[ ] Confirm that citations and reasoning paths appear below the answer.</li>
              <li>[ ] Review evidence cards for match score, confidence, and validity dates.</li>
              <li>[ ] Click &quot;Show in graph&quot; on an evidence card to inspect relationships.</li>
              <li>[ ] Open the Board drawer and review active coordination tasks on the Task Board.</li>
              <li>[ ] Open the Agents tab and inspect the Triage &rarr; Resolver &rarr; Curator relay.</li>
              <li>[ ] Open the Timeline tab and review historical versions for payments-api.</li>
              <li>[ ] Switch tenant to Beta Labs and confirm complete data isolation.</li>
              <li>[ ] Toggle light and dark modes to check theme contrast and legibility.</li>
              <li>[ ] Open the Guide from the header and close it using the Escape key.</li>
            </ul>
          </section>

          {/* 8. Glossary */}
          <section className="guide-section">
            <h2>Glossary</h2>
            <table className="guide-table">
              <thead>
                <tr>
                  <th style={{ width: "24%" }}>Term</th>
                  <th>Definition</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>memory</strong></td>
                  <td>A stored piece of operational knowledge, such as an incident summary, service fact, or runbook.</td>
                </tr>
                <tr>
                  <td><strong>tenant</strong></td>
                  <td>An isolated organizational workspace (such as Acme Corp or Beta Labs) with private records.</td>
                </tr>
                <tr>
                  <td><strong>entity</strong></td>
                  <td>A tracked component, team, user, or service represented in the system (e.g. payments-api).</td>
                </tr>
                <tr>
                  <td><strong>graph</strong></td>
                  <td>The network of connected nodes and relationships representing operational knowledge.</td>
                </tr>
                <tr>
                  <td><strong>node</strong></td>
                  <td>A single visual item in the graph, such as an Entity, Memory, Agent, or Task.</td>
                </tr>
                <tr>
                  <td><strong>link</strong></td>
                  <td>A connection joining two nodes, representing a dependency, mention, or replacement.</td>
                </tr>
                <tr>
                  <td><strong>evidence</strong></td>
                  <td>The specific stored memory records retrieved to substantiate and ground an answer.</td>
                </tr>
                <tr>
                  <td><strong>citation</strong></td>
                  <td>A reference tag identifying the exact memory card that supports a statement in the answer.</td>
                </tr>
                <tr>
                  <td><strong>reasoning path</strong></td>
                  <td>A directional chain showing how entities depend on each other (e.g. checkout-ui &rarr; payments-api).</td>
                </tr>
                <tr>
                  <td><strong>superseded</strong></td>
                  <td>An older operational fact that has been replaced by a newer update and marked inactive.</td>
                </tr>
                <tr>
                  <td><strong>conflicted</strong></td>
                  <td>A memory record identified as having contradictory or competing operational statements.</td>
                </tr>
                <tr>
                  <td><strong>task</strong></td>
                  <td>An actionable coordination assignment tracked on the Task Board.</td>
                </tr>
                <tr>
                  <td><strong>lease</strong></td>
                  <td>A temporary reservation mechanism preventing two agents from claiming the same task simultaneously.</td>
                </tr>
                <tr>
                  <td><strong>agent</strong></td>
                  <td>An automated participant dedicated to a specialized phase of inquiry triage or memory curation.</td>
                </tr>
                <tr>
                  <td><strong>handoff</strong></td>
                  <td>The orderly transfer of task context and responsibility from one agent to the next.</td>
                </tr>
                <tr>
                  <td><strong>Triage</strong></td>
                  <td>The initial agent that categorizes questions and identifies required actions.</td>
                </tr>
                <tr>
                  <td><strong>Resolver</strong></td>
                  <td>The analytical agent that synthesizes evidence to answer questions or formulate resolutions.</td>
                </tr>
                <tr>
                  <td><strong>Curator</strong></td>
                  <td>The steward agent that preserves new knowledge, updates superseded facts, and cleans records.</td>
                </tr>
                <tr>
                  <td><strong>admin key</strong></td>
                  <td>A demonstration credential required to trigger administrative actions like seeding and resetting.</td>
                </tr>
              </tbody>
            </table>
          </section>

          {/* 9. If something looks wrong */}
          <section className="guide-section">
            <h2>If something looks wrong</h2>
            <table className="guide-table">
              <thead>
                <tr>
                  <th>What you see</th>
                  <th>What it means</th>
                  <th>What to do</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><code>Offline</code> in header badge</td>
                  <td>The web application is unable to communicate with its background services.</td>
                  <td>Refresh your browser page or ask the team for assistance.</td>
                </tr>
                <tr>
                  <td><code>Degraded (Persistence Offline)</code></td>
                  <td>The persistent storage connection is temporarily unavailable.</td>
                  <td>Wait a few moments and refresh the page, or notify the team.</td>
                </tr>
                <tr>
                  <td>&quot;No past conversations for this tenant.&quot;</td>
                  <td>No previous conversations exist in this browser for the chosen organization.</td>
                  <td>Submit a question in the chat to create your first session.</td>
                </tr>
                <tr>
                  <td>&quot;No open tasks&quot; on Task Board</td>
                  <td>There are currently no active coordination tasks waiting on the board.</td>
                  <td>Click Admin and select Seed Fixtures, or report an incident in chat.</td>
                </tr>
                <tr>
                  <td>&quot;No handoffs recorded for this turn.&quot;</td>
                  <td>The most recent interaction did not produce a multi-agent relay chain.</td>
                  <td>Ask a question in chat or seed fixtures to observe agent coordination.</td>
                </tr>
                <tr>
                  <td>&quot;No memories about this entity yet.&quot;</td>
                  <td>The selected entity currently has no linked operational memories.</td>
                  <td>Choose another entity from the dropdown or seed fixtures via Admin.</td>
                </tr>
                <tr>
                  <td>&quot;No evidence retrieved for this query.&quot;</td>
                  <td>The query did not match any stored records closely enough to ground an answer.</td>
                  <td>Try asking about a known incident like inc-101 or seed fixtures.</td>
                </tr>
                <tr>
                  <td>An error message in chat response</td>
                  <td>The query could not be completed successfully.</td>
                  <td>Verify connection health in the header badge or contact the team.</td>
                </tr>
              </tbody>
            </table>
          </section>

          {/* 10. Known limits */}
          <section className="guide-section">
            <h2>Known limits</h2>
            <ul className="guide-bullet-list">
              <li>Answers are generated and delivered all at once upon completion, rather than streaming word by word.</li>
              <li>The admin key is a demonstration guardrail stored only in temporary browser session memory, not a multi-user authentication system.</li>
              <li>Custom typography relies on online web fonts and requires an active internet connection to display as intended.</li>
              <li>Active conversation sessions are preserved per tenant in browser local storage and will reset if browser site data is cleared.</li>
              <li>The interactive Memory Graph displays up to 150 nodes concurrently to guarantee smooth browser animation performance.</li>
              <li>Switching tenants initiates a fresh chat perspective, maintaining strict operational isolation across organizations.</li>
            </ul>
          </section>

          {/* 11. Screenshots */}
          <section className="guide-section">
            <h2>Screenshots</h2>
            <p>Reference gallery of interface captures illustrating key areas of the application:</p>
            <div className="guide-gallery">
              <figure className="guide-figure">
                <p className="guide-figure-desc">01. Start screen</p>
                <img src={resolveImg("01-start-page.png")} alt="OpsMemory start screen" className="guide-screenshot" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                <figcaption className="guide-caption">OpsMemory start screen overview</figcaption>
              </figure>
              <figure className="guide-figure">
                <p className="guide-figure-desc">02. Chat answer with citations and reasoning paths</p>
                <img src={resolveImg("02-chat-answer.png")} alt="Chat answer with citations and reasoning paths" className="guide-screenshot" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                <figcaption className="guide-caption">Grounded answer with citations and reasoning paths</figcaption>
              </figure>
              <figure className="guide-figure">
                <p className="guide-figure-desc">03. Retrieved evidence cards</p>
                <img src={resolveImg("03-evidence-cards.png")} alt="Retrieved evidence cards" className="guide-screenshot" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                <figcaption className="guide-caption">Retrieved evidence cards with match score and validity</figcaption>
              </figure>
              <figure className="guide-figure">
                <p className="guide-figure-desc">04. Show in graph action</p>
                <img src={resolveImg("04-show-in-graph.png")} alt="Show in graph action" className="guide-screenshot" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                <figcaption className="guide-caption">Focusing memory node in the interactive graph</figcaption>
              </figure>
              <figure className="guide-figure">
                <p className="guide-figure-desc">05. Agents coordination relay in Board drawer</p>
                <img src={resolveImg("05-board-agents.png")} alt="Agents coordination relay in Board drawer" className="guide-screenshot" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                <figcaption className="guide-caption">Multi-agent coordination relay (Triage → Resolver → Curator)</figcaption>
              </figure>
              <figure className="guide-figure">
                <p className="guide-figure-desc">06. Entity memory timeline in Board drawer</p>
                <img src={resolveImg("06-board-timeline.png")} alt="Entity memory timeline in Board drawer" className="guide-screenshot" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                <figcaption className="guide-caption">Entity memory timeline showing historical supersession</figcaption>
              </figure>
              <figure className="guide-figure">
                <p className="guide-figure-desc">07. Interactive Memory Graph</p>
                <img src={resolveImg("07-memory-graph.png")} alt="Interactive Memory Graph" className="guide-screenshot" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                <figcaption className="guide-caption">Interactive Memory Graph topology visualization</figcaption>
              </figure>
              <figure className="guide-figure">
                <p className="guide-figure-desc">08. Admin menu with seed and reset options</p>
                <img src={resolveImg("08-admin-menu.png")} alt="Admin menu with seed and reset options" className="guide-screenshot" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                <figcaption className="guide-caption">Admin menu with seed and reset options</figcaption>
              </figure>
              <figure className="guide-figure">
                <p className="guide-figure-desc">09. OpsMemory in dark theme</p>
                <img src={resolveImg("09-dark-theme.png")} alt="OpsMemory in dark theme" className="guide-screenshot" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                <figcaption className="guide-caption">OpsMemory in warm dark theme</figcaption>
              </figure>
            </div>
          </section>

          {/* 12. Team */}
          <section className="guide-section guide-team-section">
            <h2>Team</h2>
            <p>Built with care for the WeMakeDevs FalkorDB Hackathon (Track 2: Agent Memory and Coordination) by:</p>
            <div className="guide-team-list">
              <p><strong>Tanishq Garg</strong></p>
              <p><strong>Gautam Jain</strong></p>
              <p><strong>Disha Gupta</strong></p>
            </div>
            <div className="guide-footer-action">
              <button className="btn btn-primary" onClick={onClose} data-tooltip="Return to the active OpsMemory console and test the system." data-tooltip-pos="top">
                Back to OpsMemory
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
