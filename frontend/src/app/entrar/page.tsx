"use client";

import { Eye, EyeOff, LoaderCircle, LockKeyhole } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";

import { Logo } from "@/componentes/logo";
import { cadastrar, entrar, mensagemDeErro } from "@/lib/api";

type Modo = "entrar" | "cadastrar";

const MODOS: { valor: Modo; rotulo: string }[] = [
  { valor: "entrar", rotulo: "Entrar" },
  { valor: "cadastrar", rotulo: "Criar conta" },
];

const TAMANHO_MINIMO_SENHA = 8;

const campo =
  "h-12 w-full rounded-xl border border-borda-campo bg-cartao px-3.5 text-base text-texto placeholder:text-texto-suave focus:border-primaria-texto focus:outline-none focus:ring-2 focus:ring-primaria-suave sm:text-sm";
const rotulo = "mb-1.5 block text-xs font-semibold text-texto-secundario";

/** Entrada e cadastro. Ao dar certo, a guarda do layout leva para o início. */
export default function TelaEntrar() {
  const [modo, setModo] = useState<Modo>("entrar");
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [senhaVisivel, setSenhaVisivel] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const campoErro = useRef<HTMLParagraphElement>(null);
  const cadastro = modo === "cadastrar";

  function trocarModo(novo: Modo) {
    setModo(novo);
    setErro(null);
  }

  async function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (enviando) return;
    if (cadastro && senha.length < TAMANHO_MINIMO_SENHA) {
      setErro(`A senha precisa ter pelo menos ${TAMANHO_MINIMO_SENHA} caracteres.`);
      return;
    }
    setEnviando(true);
    setErro(null);
    try {
      if (cadastro) await cadastrar(nome, email, senha);
      else await entrar(email, senha);
      // A sessão gravada faz a guarda trocar de tela; este componente desmonta.
    } catch (falha) {
      setErro(mensagemDeErro(falha));
      setEnviando(false);
      requestAnimationFrame(() => campoErro.current?.focus());
    }
  }

  return (
    <main className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      <div className="px-5 pb-2 pt-[max(1rem,env(safe-area-inset-top))]">
        <Logo className="h-9 w-auto" />
      </div>

      <div className="flex flex-1 flex-col justify-center px-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-4">
        <h1 className="font-display text-2xl font-bold text-texto">
          {cadastro ? "Crie sua conta" : "Entre na sua conta"}
        </h1>
        <p className="mt-1.5 text-sm text-texto-secundario">
          {cadastro
            ? "Leva um minuto. Depois é só digitalizar."
            : "Para digitalizar e ver os documentos que você salvou."}
        </p>

        <div className="mt-6 flex rounded-full bg-secundario p-1" role="radiogroup" aria-label="Entrar ou criar conta">
          {MODOS.map((item) => (
            <button
              key={item.valor}
              type="button"
              role="radio"
              aria-checked={modo === item.valor}
              onClick={() => trocarModo(item.valor)}
              className={`min-h-10 flex-1 rounded-full text-sm font-semibold transition ${
                modo === item.valor ? "bg-primaria text-white" : "text-texto"
              }`}
            >
              {item.rotulo}
            </button>
          ))}
        </div>

        <form onSubmit={enviar} className="mt-5 space-y-4">
          {cadastro && (
            <div>
              <label htmlFor="nome" className={rotulo}>
                Nome
              </label>
              <input
                id="nome"
                name="name"
                type="text"
                required
                maxLength={80}
                autoComplete="name"
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                className={campo}
              />
            </div>
          )}

          <div>
            <label htmlFor="email" className={rotulo}>
              E-mail
            </label>
            <input
              id="email"
              name="email"
              type="email"
              required
              maxLength={254}
              autoComplete={cadastro ? "email" : "username"}
              autoCapitalize="none"
              spellCheck={false}
              inputMode="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={campo}
            />
          </div>

          <div>
            <label htmlFor="senha" className={rotulo}>
              Senha
            </label>
            <div className="relative">
              <input
                id="senha"
                name="password"
                type={senhaVisivel ? "text" : "password"}
                required
                maxLength={128}
                autoComplete={cadastro ? "new-password" : "current-password"}
                aria-describedby={cadastro ? "dica-senha" : undefined}
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                className={`${campo} pr-12`}
              />
              <button
                type="button"
                onClick={() => setSenhaVisivel((v) => !v)}
                aria-label={senhaVisivel ? "Esconder a senha" : "Mostrar a senha"}
                aria-pressed={senhaVisivel}
                className="absolute right-1 top-1/2 flex size-10 -translate-y-1/2 items-center justify-center rounded-lg text-texto-secundario hover:bg-secundario hover:text-texto"
              >
                {senhaVisivel ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
              </button>
            </div>
            {cadastro && (
              <p id="dica-senha" className="mt-1.5 text-xs text-texto-suave">
                Pelo menos {TAMANHO_MINIMO_SENHA} caracteres.
              </p>
            )}
          </div>

          <p
            id="erro-entrada"
            ref={campoErro}
            tabIndex={-1}
            role="alert"
            className={`rounded-xl border border-perigo/40 bg-perigo/10 px-3.5 py-2.5 text-sm text-texto focus:outline-none ${erro ? "" : "hidden"}`}
          >
            {erro}
          </p>

          <button
            type="submit"
            disabled={enviando}
            className="flex min-h-[52px] w-full items-center justify-center gap-2 rounded-xl bg-primaria font-display text-sm font-bold text-white shadow-sm transition hover:bg-primaria-hover active:scale-[0.98] disabled:opacity-60"
          >
            {enviando && <LoaderCircle className="size-5 animate-spin" aria-hidden />}
            {enviando ? (cadastro ? "Criando a conta…" : "Entrando…") : cadastro ? "Criar conta" : "Entrar"}
          </button>
        </form>

        <p className="mt-6 flex items-start gap-2 text-xs leading-relaxed text-texto-suave">
          <LockKeyhole className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          Cada conta vê só os próprios documentos, e a senha fica guardada de um jeito que ninguém consegue ler.
        </p>
      </div>
    </main>
  );
}
