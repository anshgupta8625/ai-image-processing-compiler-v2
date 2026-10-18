import Modal from './Modal'
import { COMMANDS, TIPS } from '../data/commands'

export default function InfoModal({ limits, onClose }) {
  return (
    <Modal
      title="Command guide"
      subtitle="Every command the language has, what its parameters mean, and what the optimiser does with it."
      onClose={onClose}
    >
      <div className="cmd-grid">
        {COMMANDS.map((cmd) => {
          const params = cmd.params(limits)
          return (
            <article className="cmd-card" key={cmd.name}>
              <h3>{cmd.name}</h3>
              <code className="cmd-syntax">{cmd.syntax}</code>
              <p>{cmd.summary}</p>

              {params.length > 0 && (
                <dl className="cmd-params">
                  {params.map(([name, text]) => (
                    <div key={name}>
                      <dt>{name}</dt>
                      <dd>{text}</dd>
                    </div>
                  ))}
                </dl>
              )}

              <p className="cmd-opt"><strong>Optimiser:</strong> {cmd.optimiser}</p>
              <code className="cmd-example">{cmd.example}</code>
            </article>
          )
        })}
      </div>

      <h3 className="modal-section">Good to know</h3>
      <ul className="tips">
        {TIPS.map((tip) => <li key={tip}>{tip}</li>)}
      </ul>
    </Modal>
  )
}
