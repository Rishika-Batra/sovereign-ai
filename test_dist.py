import asyncio
from app.ai_gateway.gateway import gateway

async def main():
    q = await gateway.embed("describe WhatsApp Image 2026-10-04 at 7.25.09 PM.jpeg image")
    t1 = await gateway.embed("Rishika Batra\nFrontend Developer\nExperience: 5 years\nSkills: React, Next.js")
    t2 = await gateway.embed("A pink sticky note with handwritten text... Frontend, Backend, Database...")
    
    import numpy as np
    q_np = np.array(q)
    t1_np = np.array(t1)
    t2_np = np.array(t2)
    
    def dist(a, b):
        return 1.0 - (np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
        
    print(f"Dist to resume: {dist(q_np, t1_np)}")
    print(f"Dist to image desc: {dist(q_np, t2_np)}")

if __name__ == "__main__":
    asyncio.run(main())
