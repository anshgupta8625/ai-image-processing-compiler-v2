import Modal from './Modal'
import { COURSE, PROJECT, STACK, TEAM } from '../data/team'

const initials = (name) =>
  name.split(' ').filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase()

export default function ProfileModal({ onClose }) {
  return (
    <Modal title={PROJECT.title} subtitle="Project profile" onClose={onClose}>
      <p className="profile-blurb">{PROJECT.tagline}</p>

      <h3 className="modal-section">Team</h3>
      <ul className="team">
        {TEAM.map((member) => (
          <li key={member.id}>
            <span className="avatar" aria-hidden="true">{initials(member.name)}</span>
            <span>
              <strong>{member.name}</strong>
              <small>{member.id}</small>
            </span>
          </li>
        ))}
      </ul>

      <h3 className="modal-section">Course</h3>
      <dl className="course">
        {COURSE.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      <h3 className="modal-section">Built with</h3>
      <ul className="stack">
        {STACK.map((item) => <li key={item}>{item}</li>)}
      </ul>

      <div className="profile-links">
        <a href={PROJECT.repo} target="_blank" rel="noopener noreferrer">Source on GitHub ↗</a>
        <a href={PROJECT.demo} target="_blank" rel="noopener noreferrer">Live demo ↗</a>
      </div>
    </Modal>
  )
}
