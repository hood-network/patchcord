module.exports = {
  apps : [
      {
        name: "litecord",
        script: "pipenv run hypercorn run:app",
        watch: true,
      }
  ]
}
