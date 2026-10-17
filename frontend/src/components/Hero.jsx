export default function Hero({ compact = false }) {
  return (
    <section className={`hero ${compact ? "compact" : ""}`}>
      <h1 className="hero-title">
        AGENT MEMORY AND <span>COORDINATION</span>
      </h1>
    </section>
  );
}