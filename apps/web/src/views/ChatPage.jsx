import { SectionCard } from "../components/SectionCard";
import { chatMessages, chatThreads } from "../data/mock";
import { ChatMessageForm } from "../forms/ChatMessageForm";

export function ChatPage() {
  return (
    <div className="chat-layout">
      <SectionCard
        title="Canales operativos"
        subtitle="Coordinacion entre bodegas, compras y despacho"
      >
        <div className="thread-list">
          {chatThreads.map((thread) => (
            <article key={thread.id} className="thread-item">
              <div>
                <strong>{thread.channel}</strong>
                <p>{thread.lastMessage}</p>
                <span>{thread.owner}</span>
              </div>
              {thread.unread ? (
                <span className="thread-unread">{thread.unread}</span>
              ) : null}
            </article>
          ))}
        </div>
      </SectionCard>

      <SectionCard
        title="Conversacion"
        subtitle="Hilo operativo vinculado a reposicion"
        actions={<button className="ghost-button">Crear solicitud</button>}
      >
        <div className="chat-messages">
          {chatMessages.map((message) => (
            <article key={message.id} className="chat-message">
              <div className="chat-message-head">
                <strong>{message.author}</strong>
                <span>{message.role}</span>
                <time>{message.time}</time>
              </div>
              <p>{message.text}</p>
            </article>
          ))}
        </div>
        <ChatMessageForm />
      </SectionCard>
    </div>
  );
}
