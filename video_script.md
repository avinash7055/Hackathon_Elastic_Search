# SignalShield AI - Devpost Video Script

**Target Length:** 2.5 to 3 minutes
**Tools Needed:** A screen recorder (OBS Studio, Windows Game Bar `Win + G`, or Loom) and a microphone.

---

## 🎬 Part 1: The Pitch (0:00 - 0:45)
*What to show on screen: Open the `presentation.html` file in your browser and let the first 3 slides auto-play while you speak.*

**[Speak]:**  
"Hi everyone, welcome to SignalShield AI. 

Pharmacovigilance—the process of monitoring drugs for safety after they hit the market—is a $5 billion dollar industry. The FDA receives over 800,000 adverse event reports every year, and manual reviewers just can't keep up. It takes weeks to detect a dangerous safety signal in the data.

We wanted to fix this. So we built SignalShield AI for the Elastic Agent Builder Hackathon. 

It's a multi-agent AI system powered by Elasticsearch, ELSER semantic search, Groq, and LangGraph that transforms weeks of manual safety review into exactly 30 seconds."

---

## 💻 Part 2: The Dashboard & Routing (0:45 - 1:15)
*What to show on screen: Switch to your React Frontend (http://localhost:5173). Show the Dashboard UI. Type in the chat box but don't hit enter yet.*

**[Speak]:**  
"Let's jump into the live application. 

At the core of our system is the Master Orchestrator agent. It understands natural language and routes user queries to 7 distinct execution paths.

We built 4 specialized AI Agents deployed natively into the Elastic Kibana Converse API, equipped with 11 custom ES|QL tools that can instantly run complex statistical aggregations on 500,000 synthetic FAERS records."

---

## 🔍 Part 3: Live Demo - RAG & ELSER (1:15 - 1:45)
*What to show on screen: Type: *"How is Proportional Reporting Ratio (PRR) calculated in pharmacovigilance?"* Hit Enter. Wait for the response.*

**[Speak]:**  
"First, let's look at our Knowledge Base route. Pharmacovigilance is highly complex, so we built a RAG pipeline using Elastic's ELSER v2 semantic vector search. 

When I ask how statistical methods like PRR are calculated, the system doesn't guess. It retrieves the exact methodology directly from our indexed guidelines, completely preventing AI hallucinations."

---

## 🚨 Part 4: Live Demo - Signal Investigation (1:45 - 2:30)
*What to show on screen: Type: *"Run a full safety investigation on Cardizol-X"* and hit enter. **THIS IS THE MOST IMPORTANT PART!** Let the audience watch the 'Reasoning Trace' on the right side of your screen as the agents use their ES|QL tools in real-time.*

**[Speak]:**  
"Now for the real power: autonomous data investigation. I'm going to ask the system to investigate the drug 'Cardizol-X'. 

Watch the Agent Transparency trace on the right. The Master Orchestrator immediately routes this to our Case Investigator and Safety Reporter agents. You can see them dynamically invoking our custom ES|QL tools. 

Right now, it's querying hundreds of thousands of records in Elasticsearch, calculating the Proportional Reporting Ratios, and checking for temporal spikes in the last 90 days versus the 365-day baseline.

*(Pause for a couple of seconds while it streams the final answer)*

And in just seconds, it identified a critical safety signal—a massive 3.4x spike in fatal cardiac arrhythmias for Cardizol-X, and generated a complete, MedWatch-style regulatory report."

---

## 📄 Part 5: The Export & Wrap Up (2:30 - 3:00)
*What to show on screen: Click the "Download PDF" button on the UI to show that the report can be exported. Then open the network architecture slide from `presentation.html`.*

**[Speak]:**  
"Reviewers can instantly export this assessment as a formatted PDF for regulatory submission.

By combining the blazing speed of Groq LLMs with the statistical power of ES|QL and the Elastic Agent Builder, SignalShield AI proves that we can completely automate complex data-science workflows and ultimately, save patient lives.

The code is fully open-source on GitHub, complete with Docker CI/CD. 

Thank you to Elastic and Devpost for this amazing hackathon!" 

*(End Video)*

---

### 💡 Recording Tips:
1. Practice the script 2-3 times before hitting record so you sound natural.
2. Make sure your local backend (`uvicorn app.api:app --reload`) and frontend (`npm run dev`) are both running smoothly before you start.
3. Keep your mouse movements smooth and deliberate. Don't wildly shake the cursor.
4. If you stumble on a word, just keep going! Enthusiasm and a working demo matter much more than a perfect voiceover.
