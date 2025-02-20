Esempio di Workflow Completo

Se hai già il tuo script Pulumi pronto, il workflow tipico sarà:

 1. Assicurati di essere loggato
    
pulumi login --local

 3. Controlla cosa succederà prima di applicare le modifiche
    
pulumi preview

 5. Crea l'infrastruttura
    
pulumi up

 7. Controlla le risorse create
    
pulumi stack output
pulumi state list

 9. Se vuoi distruggere tutto
     
pulumi destroy
